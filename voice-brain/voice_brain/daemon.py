"""The daemon: owns the mic, the socket, the overlay pill, and the pipeline.

Socket protocol (unix domain, one JSON request per connection):
    {"cmd": "toggle"}                     arm / force-finalize current capture
    {"cmd": "cancel"}                    discard in-flight session
    {"cmd": "say", "text": "..."}        route text through the pipeline (no mic)
    {"cmd": "status"}                    -> {"state": "...", "last": "..."}
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from datetime import datetime

from . import notify as notify_mod
from .audio import CaptureError, CaptureState, MicCapture
from .intent import Kind, classify
from .prompts import intent_classify
from .vault import parse_frontmatter

END_DICTATION = ("end dictation", "stop dictation", "fim da ditacao")


class Daemon:
    def __init__(self, app, ui):
        self.app = app
        self.ui = ui
        self._drain_pending()
        self.app = app
        self.ui = ui
        self.state = "idle"
        self.last_result = "—"
        self._capture: MicCapture | None = None
        self._session_lock = threading.Lock()
        self._dictation = False
        self._shutdown = threading.Event()
        self._pair_pin: str | None = None
        self._pair_expires: float = 0.0

    def _drain_pending(self) -> None:
        """Standalone mode: process any utterances the relay couldn't deliver."""
        if str(self.app.cfg.get("daemon.mode", "relay")) != "standalone":
            return
        import json
        from .archive import TranscriptArchive
        pending = self.app.cfg.state_dir() / "pending.jsonl"
        if not pending.exists():
            return
        lines = [ln for ln in pending.read_text().splitlines() if ln.strip()]
        archive = TranscriptArchive(self.app.cfg)
        for line in lines:
            try:
                entry = json.loads(line)
                text = entry.get("text", "").strip()
                if text:
                    archive.append(text, route="spool-drain", source="spool")
                    self.dispatch(text)
            except (json.JSONDecodeError, Exception):
                continue
        pending.write_text("")
        print(f"[spool] drained {len(lines)} pending utterance(s)")

    # ------------------------------------------------------------------ socket server

    def _serve_forever(self) -> None:
        sock_path = self.app.cfg.socket_path
        sock_path.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(sock_path))
        os.chmod(sock_path, 0o600)
        server.listen(8)
        server.settimeout(1.0)
        while not self._shutdown.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            threading.Thread(target=self._handle_conn, args=(conn,), daemon=True).start()
        server.close()
        sock_path.unlink(missing_ok=True)

    def _handle_conn(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(10)
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            if not data:
                conn.close()
                return
            cmd = json.loads(data.decode("utf-8", errors="replace").strip())
            resp = self.handle_command(cmd)
            conn.sendall(json.dumps(resp).encode() + b"\n")
        except Exception as exc:
            try:
                conn.sendall(json.dumps({"ok": False, "error": str(exc)}).encode() + b"\n")
            except Exception:
                pass
        finally:
            conn.close()

    # ------------------------------------------------------------------ commands

    def handle_command(self, cmd: dict) -> dict:
        op = str(cmd.get("cmd", "")).lower()
        if op == "toggle":
            return self.cmd_toggle()
        if op == "cancel":
            return self.cmd_cancel()
        if op == "status":
            return {"ok": True, "state": self.state, "last": self.last_result,
                    "dictation": self._dictation}
        if op == "pair":
            # LocalSend-style pairing: generate a short-lived PIN the user enters
            # on the phone; /pair exchanges the PIN for the auth token.
            import secrets
            self._pair_pin = f"{secrets.randbelow(1_000_000):06d}"
            self._pair_expires = time.time() + 600  # 10 minutes
            return {"ok": True, "pin": self._pair_pin, "expires_in": 600}
        if op == "say":
            text = str(cmd.get("text", "")).strip()
            if not text:
                return {"ok": False, "error": "empty text"}
            threading.Thread(target=self._process_text, args=(text, "text"),
                            daemon=True).start()
            return {"ok": True, "state": "processing"}
        if op == "quit":
            self._shutdown.set()
            return {"ok": True}
        return {"ok": False, "error": f"unknown command: {op}"}

    def pair_is_valid(self, pin: str) -> bool:
        import time as _t
        return (self._pair_pin is not None and _t.time() < self._pair_expires
                and str(pin).strip() == self._pair_pin)

    def cmd_toggle(self) -> dict:
        if self.state == "idle":
            self._start_session()
            return {"ok": True, "state": self.state}
        # armed/recording -> force finalize and process
        if self._capture:
            self._capture.finalize_now()
        return {"ok": True, "state": self.state}

    def cmd_cancel(self) -> dict:
        if self._capture:
            self._capture.cancel()
        self._dictation = False
        self.state = "idle"
        self.ui.state("idle")
        return {"ok": True, "state": "idle"}

    # ------------------------------------------------------------------ sessions

    def _start_session(self) -> None:
        if not self._session_lock.acquire(blocking=False):
            return
        self._session_lock.release()
        threading.Thread(target=self._session_worker, daemon=True).start()

    def _session_worker(self) -> None:
        with self._session_lock:
            try:
                self.state = "armed"
                self.ui.state("armed")
                capture = MicCapture(
                    self.app.cfg,
                    on_state=lambda s: self.ui.state("recording" if s == "recording" else s),
                    on_level=lambda v: self.ui.state("recording", level=v),
                )
                self._capture = capture
                capture.arm()
            except CaptureError as exc:
                self.state = "idle"
                self._capture = None
                self.ui.state("error", str(exc))
                notify_mod.notify_error("Voice Brain", str(exc))
                return

            result = capture.result()
            self._capture = None

            if result.state == CaptureState.DONE and result.wav_path:
                self._process_wav(result.wav_path)
            elif result.state == CaptureState.TIMEOUT:
                self.ui.state("timeout")
                notify_mod.notify("⏱️ Voice Brain", "Nothing heard.", timeout_ms=3000)
            elif result.state == CaptureState.CANCELLED:
                self.ui.state("cancelled")

            self.state = "idle"
            if self._dictation:
                # continuous mode: re-arm for the next utterance
                self._start_session()

    def _process_wav(self, wav_path) -> None:
        self.state = "transcribing"
        self.ui.state("transcribing")
        try:
            prompt = self.app.glossary.whisper_prompt()
            tr = self.app.stt.transcribe(wav_path, initial_prompt=prompt or None)
        except Exception as exc:
            self.ui.state("error", str(exc))
            notify_mod.notify_error("Transcription failed", str(exc))
            return
        self._process_text(tr.text, "voice", confidence=tr.avg_logprob)

    # ------------------------------------------------------------------ routing

    def _process_text(self, text: str, source: str,
                      confidence: float | None = None) -> tuple | None:
        """Route one utterance end-to-end. Every path returns (state, title, body)
        where possible; every standalone capture leaves a raw transcript note in
        the Voice Brain Inbox before any LLM runs."""
        if not text.strip():
            self.ui.state("timeout")
            return None
        # plugin is the control center: hot-reload vault-synced settings
        # (Voice Brain Settings/settings.md — models, language, overlay, silence)
        try:
            self.app.settings_sync.check()
        except Exception:
            pass
        if source == "voice" and self._dictation and any(
                text.lower().startswith(e) for e in END_DICTATION):
            self._dictation = False
            self.ui.result("success", "🎙️ Dictation ended", f"{text.strip()}")
            return "success", "Dictation ended", text.strip()

        mode = str(self.app.cfg.get("daemon.mode", "relay"))
        if mode == "standalone":
            # raw whisper transcript -> Voice Brain Inbox, before any LLM runs
            # (survives LLM failures and undo — never lose input)
            try:
                from .intent import classify as _classify
                from .notes import save_raw_transcript
                route = _classify(text, self.app.cfg,
                                  patterns=self.app.patterns).kind.value
                save_raw_transcript(self.app.vault, self.app.cfg, text,
                                    source, route, confidence)
            except Exception as exc:
                print(f"[transcript] raw save failed: {exc}")

        if mode == "relay":
            # the plugin saves the raw transcript on its side
            self.state = "processing"
            self.ui.state("processing")
            summary = self.app.relay.send(text, source="hotkey", confidence=confidence)
            self.ui.result("success", summary.split("\n")[0], summary)
            self.last_result = summary
            self.state = "idle"
            if self._dictation:
                self._start_session()
            return

        self.state = "processing"
        self.ui.state("processing")
        state_kind, title, body = self.dispatch(text, confidence=confidence)
        # spoken-history archive (JSONL) — searchable "what did I say about X?"
        try:
            self.app.archive.append(text, route=state_kind, source=source,
                                    confidence=confidence)
        except Exception:
            pass
        self.ui.result(state_kind, title, body)
        self.last_result = title
        self.state = "idle"
        return state_kind, title, body
        self.last_result = title
        self.state = "idle"

    def dispatch(self, text: str, confidence: float | None = None):
        """Route an utterance. Returns (ui_state, title, body). Never raises —
        the capture-everything safety net catches failures."""
        intent = classify(text, self.app.cfg, patterns=self.app.patterns)
        app = self.app
        try:
            if intent.kind is Kind.DREAM:
                files = app.dream.handle(intent.payload or intent.text)
                if not files:
                    return ("error", "🤔 Not a dream?", "Nothing dream-like found in that.")
                body = "\n".join(files)
                return ("dream", f"💜 {len(files)} dream{'s' if len(files) > 1 else ''} saved", body)

            if intent.kind is Kind.NOTE:
                # user pattern, e.g. "I have an idea ..." -> polished note in Projects
                rel = app.notes.create_polished(intent.payload or intent.text,
                                                folder=intent.folder)
                return ("note", "🗒️ Note created", rel)

            if intent.kind is Kind.CAPTURE:
                rel = app.notes.capture(intent.payload or intent.text)
                return ("success", "📥 Saved to inbox", rel)

            if intent.kind is Kind.SCRATCH:
                result = app.ledger.undo_last()
                return ("success", "🔄 Undone", result)

            if intent.kind is Kind.JOURNAL or intent.kind is Kind.STAT_LOG:
                path = app.journal.handle(intent.payload or intent.text)
                rel = path.relative_to(app.vault.root).as_posix()
                return ("journal", "📝 Logged", rel)

            if intent.kind is Kind.STATS:
                from datetime import date as Date
                out = app.stats.generate(Date.today())
                doc = json.loads(out.read_text())
                return ("stats", "📊 Stats generated",
                        app.stats.summarize_for_notification(doc) + f"\n{out.name}")

            if intent.kind is Kind.BRIEF:
                return ("query", "🌅 Briefing", app.briefer.brief())

            if intent.kind is Kind.DICTATION:
                self._dictation = True
                self._start_session()
                return ("success", "🎙️ Dictation started", "Speak freely — 'end dictation' stops.")

            # GENERAL -> cheap LLM intent classification
            doc = app.llm.generate(intent_classify(text), lane="quick", json_mode=True)
            kind = str(doc.get("kind", "capture"))
            if kind == "create_note":
                rel = app.notes.create(text)
                return ("note", "🗒️ Note created", rel)
            if kind == "query":
                return ("query", "💬 Answer", app.query.answer(text))
            if kind == "organize":
                plan = app.organizer.plan()
                return ("success", "🗂️ Organize plan drafted",
                        f"{plan}\nApply with: voice-brain apply-plan {plan}")
            # capture -> polish the raw transcript into a clean note (inbox)
            rel = app.notes.create_polished(text)
            return ("note", "🗒️ Note captured", rel)

        except Exception as exc:
            # never lose input: verbatim capture + loud error
            try:
                rel = app.notes.capture(text)
                return ("error", "❌ Something went wrong", f"{exc}\nWords saved to {rel}")
            except Exception:
                return ("error", "❌ Something went wrong", str(exc))
