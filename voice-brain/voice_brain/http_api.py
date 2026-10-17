"""Standalone capture API: the Python daemon hosts the same HTTP surface the
Obsidian plugin hosts in relay mode — so the Android app (and anything else)
works identically in both deployment profiles.

  GET  /health
  POST /utterance   {"text": "...", "source": "...", "ts": ...}   (pre-transcribed)
  POST /api/capture raw audio bytes + X-VB-Filename header          (phone recordings)

Token auth via X-VB-Token (required when binding beyond localhost).
"""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .stt import STTUnavailable, Transcription

_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```")


class CaptureAPI:
    def __init__(self, daemon, host: str, port: int, token: str):
        self.daemon = daemon
        self.host = host
        self.port = port
        self.token = token
        self._server: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        if self._server:
            return
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence request logging
                pass

            def do_GET(self):
                if self.path.startswith("/health"):
                    self._json({"ok": True})
                elif self.path.startswith("/whoami"):
                    # token-verified identity check (used by the phone's "Test connection")
                    if api.authorized(self.headers.get("X-VB-Token")):
                        import socket as _s
                        self._json({"ok": True, "name": _s.gethostname()})
                    else:
                        self._json({"ok": False, "error": "bad or missing token"}, 401)
                else:
                    self._json({"ok": False, "error": "not found"}, 404)

            def do_POST(self):
                try:
                    if self.path.startswith("/pair"):
                        length = int(self.headers.get("Content-Length", 0))
                        body = self.rfile.read(length)
                        code, doc = api.handle_pair(body)
                        self._json(doc, code)
                        print(f"[http] POST /pair from {self.client_address[0]} -> {code}")
                        return
                    if not api.authorized(self.headers.get("X-VB-Token")):
                        print(f"[http] POST {self.path} from {self.client_address[0]} -> 401 (bad token)")
                        self._json({"ok": False, "error": "bad or missing token"}, 401)
                        return
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length)
                    if self.path.startswith("/utterance"):
                        self._json(api.handle_utterance(body))
                        print(f"[http] POST /utterance from {self.client_address[0]} -> 200")
                    elif self.path.startswith("/api/capture"):
                        self._json(api.handle_capture(body, self.headers))
                        print(f"[http] POST /api/capture from {self.client_address[0]} -> 200")
                    else:
                        self._json({"ok": False, "error": "not found"}, 404)
                except Exception as exc:  # loud errors to the client, never to the caller
                    print(f"[http] POST {self.path} from {self.client_address[0]} -> 500: {exc}")
                    self._json({"ok": False, "error": str(exc)}, 500)

            def _json(self, doc, code=200):
                payload = json.dumps(doc).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True,
                         name="vb-http-api").start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None

    def authorized(self, provided: str | None) -> bool:
        if not self.token:
            return self.host in ("127.0.0.1", "localhost")
        return provided == self.token

    def handle_pair(self, body: bytes):
        """PIN-for-token exchange (LocalSend style). The PIN comes from
        `voice-brain pair` on the laptop and lives 10 minutes."""
        import json as _json
        try:
            doc = _json.loads(body.decode("utf-8", errors="replace"))
            pin = str(doc.get("pin", "")).strip()
            if self.daemon.pair_is_valid(pin):
                token = str(self.daemon.app.cfg.get("daemon.token", ""))
                return 200, {"ok": True, "token": token,
                             "name": "laptop",
                             "url": self.daemon_url()}
            return 401, {"ok": False, "error": "invalid or expired PIN — run 'voice-brain pair' on the laptop"}
        except Exception as exc:
            return 500, {"ok": False, "error": str(exc)}

    def daemon_url(self) -> str:
        import socket as _s
        try:
            hostname = _s.gethostbyname(_s.gethostname())
        except OSError:
            hostname = self.host
        return f"http://{hostname}:{self.port}"

    # ------------------------------------------------------------------ handlers

    def handle_utterance(self, body: bytes) -> dict:
        doc = json.loads(body.decode("utf-8", errors="replace"))
        text = str(doc.get("text", "")).strip()
        if not text:
            return {"ok": False, "error": "empty text"}
        result = self.daemon._process_text(text, str(doc.get("source", "phone")))
        if result:
            _, title, detail = result
            return {"ok": True, "summary": f"{title}\n{detail}".strip()}
        return {"ok": True, "summary": self.daemon.last_result}

    def handle_capture(self, body: bytes, headers) -> dict:
        app = self.daemon.app
        content_type = str(headers.get("Content-Type", ""))
        if "application/json" in content_type:
            doc = json.loads(body.decode("utf-8", errors="replace"))
            if doc.get("audioBase64"):
                import base64
                body = base64.b64decode(doc["audioBase64"])
                filename = str(doc.get("filename", "capture.m4a"))
            else:
                return self.handle_utterance(body)
        else:
            filename = str(headers.get("X-VB-Filename", f"capture-{int(time.time())}.wav"))

        spool = app.cfg.spool_dir()
        spool.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix or ".wav"
        tmp = spool / f"phone-{int(time.time() * 1000)}{suffix}"
        tmp.write_bytes(body)
        try:
            tr: Transcription = app.stt.transcribe_file(tmp, initial_prompt=app.glossary.whisper_prompt() or None)
        except STTUnavailable as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            tmp.unlink(missing_ok=True)
            for p in spool.glob("phone-*.vb.wav"):
                p.unlink(missing_ok=True)
        if not tr.text:
            return {"ok": False, "error": "empty transcription"}
        result = self.daemon._process_text(tr.text, "phone", tr.avg_logprob)
        if result:
            _, title, detail = result
            return {"ok": True, "summary": f"{title}\n{detail}".strip()}
        return {"ok": True, "summary": self.daemon.last_result}
