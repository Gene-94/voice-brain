"""voice-brain CLI entrypoint.

Commands:
  doctor [--mic] [--setup]   environment check; --setup installs what it can
  daemon                     run the background daemon (mic + socket + overlay)
  toggle                     arm capture / force-finalize (bind to SUPER+ALT+V)
  cancel                     discard in-flight capture
  status                     daemon state
  say "text"                 route text through the pipeline without the mic
  replay <wav> [--route X]   transcribe a WAV and route it
  generate-stats [--date D]  stats for today (or D) — same path as voice/nightly
  brief                      morning briefing (yesterday's stats + TODOs)
  undo                       revert last daemon write
  apply-plan <file.json>     apply a reviewed organize plan
  search "query"             vault Q&A from the terminal
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import date as Date
from pathlib import Path

from . import __version__
from .client import send


def cmd_doctor(args, cfg) -> int:
    from .stt import WhisperSTT
    checks: list[tuple[str, bool, str]] = []

    vault = cfg.vault_root()
    checks.append(("vault exists", vault.exists(), str(vault)))
    checks.append(("vault writable", vault.exists() and _writable(vault), str(vault)))
    models = cfg.models_dir()
    checks.append(("models dir", models.exists(), str(models)))

    stt = WhisperSTT(cfg)
    checks.append(("whisper-cli", stt.cli_available(),
                   "pacman -S whisper-cpp" if not stt.cli_available() else "found"))
    checks.append((f"whisper model ({stt.model_name})", stt.model_present(),
                   str(stt.model_path()) if not stt.model_present() else "downloaded"))

    from .llm import OllamaClient
    llm = OllamaClient(cfg)
    up = llm.is_up()
    checks.append(("ollama reachable", up, llm.base_url))
    if up:
        quick = str(cfg.get("llm.model_quick"))
        deep = str(cfg.get("llm.model_deep"))
        checks.append((f"{quick} (quick lane)", llm.model_present(quick),
                       f"ollama pull {quick}"))
        checks.append((f"{deep} (deep lane)", llm.model_present(deep),
                       f"ollama pull {deep}"))
    for binary in ("parec", "pw-record", "pactl", "notify-send", "ffmpeg"):
        present = bool(shutil.which(binary))
        checks.append((binary, present, "found" if present else "MISSING"))

    from .audio import resolve_source, source_is_muted
    source = resolve_source(cfg)
    checks.append(("microphone source", bool(source), source or "no source found"))
    if source:
        muted = source_is_muted(source)
        checks.append(("mic unmuted", not muted,
                       "MUTED — privacy kill-switch" if muted else "live"))

    from .relay import Relay
    relay = Relay(cfg)
    daemon_mode = str(cfg.get("daemon.mode", "relay"))
    checks.append(("daemon mode", True,
                   daemon_mode + (" — plugin optional (UI only)" if daemon_mode == "standalone"
                                  else " — relay to Obsidian plugin")))
    if daemon_mode == "relay":
        checks.append(("obsidian plugin server", relay.is_plugin_up(),
                       f"{relay.url}/health (offline captures go to the pending spool — that's OK)"))

    ok = all(passed for _, passed, _ in checks)
    print("Voice Brain doctor")
    print("=" * 60)
    for name, passed, detail in checks:
        mark = "✅" if passed else "❌"
        print(f" {mark} {name:28s} {detail}")
    print("=" * 60)

    if args.setup:
        _doctor_setup(cfg, stt)
    if args.mic:
        _mic_meter(cfg)
    print("ALL GOOD 👍" if ok else "Some checks failed — see above.")
    return 0 if ok else 1


def _writable(path: Path) -> bool:
    try:
        probe = path / ".vb-write-probe"
        probe.write_text("ok")
        probe.unlink()
        return True
    except OSError:
        return False


def _doctor_setup(cfg, stt) -> None:
    print("\n--setup: installing what I can…")
    from .app import build_app
    app = build_app(cfg)
    created = app.vault.ensure_folders()
    for folder in created:
        print(f"  created vault folder: {folder}")
    try:
        stt.ensure_model()
        print(f"  whisper model ready: {stt.model_path()}")
    except Exception as exc:
        print(f"  whisper model download failed: {exc}")
    if not stt.cli_available():
        print("  install whisper.cpp manually: sudo pacman -S whisper-cpp")


def _mic_meter(cfg, seconds: float = 5.0) -> None:
    """Live RMS meter to calibrate vad_start_rms."""
    from .audio import MicCapture
    print(f"\n--mic: live level meter for {seconds:.0f}s — SPEAK NORMALLY to calibrate…")
    levels: list[float] = []

    def on_level(v: float) -> None:
        levels.append(v)
        bar = "#" * int(v * 60)
        print(f"\r  {' ' * 62}\r  {bar}", end="", flush=True)

    cap = MicCapture(cfg, on_level=on_level)
    cap.arm()
    t0 = time.time()
    while time.time() - t0 < seconds:
        time.sleep(0.05)
        if cap._state.value == "recording":
            break
    cap.cancel()
    print()
    if levels:
        peak = max(levels)
        print(f"  peak level: {peak:.3f}  →  suggested vad_start_rms ≈ {max(0.01, peak / 3):.3f}")
        print(f"  (current config: {cfg.get('audio.vad_start_rms')})")
    else:
        print("  no input received — check the mic.")


def cmd_generate_stats(args, cfg) -> int:
    from .app import build_app
    app = build_app(cfg)
    day = Date.fromisoformat(args.date) if args.date else Date.today()
    out = app.stats.generate(day)
    doc = json.loads(out.read_text())
    print(f"Wrote {out}")
    print(app.stats.summarize_for_notification(doc))
    return 0


def cmd_replay(args, cfg) -> int:
    from .app import build_app
    from .audio import CaptureState, MicCapture  # noqa: F401
    from .daemon import Daemon
    from .ui import NullUI
    app = build_app(cfg)
    daemon = Daemon(app, NullUI())
    wav = Path(args.wav)
    if wav.suffix != ".wav":
        print("replay expects a 16 kHz mono WAV"); return 1
    tr = app.stt.transcribe(wav, initial_prompt=app.glossary.whisper_prompt() or None)
    print(f"Transcript: {tr.text!r} (logprob {tr.avg_logprob})")
    if args.route:
        text = tr.text
        if args.route == "dream":
            files = app.dream.handle(text)
            print("Created:", files); return 0
        if args.route == "journal":
            print("Wrote:", app.journal.handle(text)); return 0
    state, title, body = daemon.dispatch(tr.text)
    print(f"[{state}] {title}\n{body}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voice-brain",
                                     description="Local voice-first knowledge assistant")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", help="config yaml path")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("doctor"); p.add_argument("--mic", action="store_true")
    p.add_argument("--setup", action="store_true")
    sub.add_parser("daemon")
    sub.add_parser("toggle")
    sub.add_parser("cancel")
    sub.add_parser("status")
    p = sub.add_parser("say"); p.add_argument("text")
    p = sub.add_parser("generate-stats"); p.add_argument("--date", help="YYYY-MM-DD")
    sub.add_parser("brief")
    sub.add_parser("undo")
    p = sub.add_parser("replay"); p.add_argument("wav"); p.add_argument("--route")
    p = sub.add_parser("apply-plan"); p.add_argument("plan")
    p = sub.add_parser("search"); p.add_argument("query")
    sub.add_parser("pair")

    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 1

    from .config import load_config
    cfg = load_config(args.config)

    if args.cmd == "doctor":
        return cmd_doctor(args, cfg)
    if args.cmd == "daemon":
        return cmd_daemon(cfg)
    if args.cmd == "toggle":
        return _print(send(cfg, {"cmd": "toggle"}))
    if args.cmd == "cancel":
        return _print(send(cfg, {"cmd": "cancel"}))
    if args.cmd == "status":
        return _print(send(cfg, {"cmd": "status"}))
    if args.cmd == "say":
        return _print(send(cfg, {"cmd": "say", "text": args.text}))
    if args.cmd == "generate-stats":
        return cmd_generate_stats(args, cfg)
    if args.cmd == "brief":
        from .app import build_app
        app = build_app(cfg)
        print(app.briefer.brief())
        return 0
    if args.cmd == "undo":
        from .app import build_app
        app = build_app(cfg)
        try:
            print(app.ledger.undo_last())
            return 0
        except Exception as exc:
            print(f"❌ {exc}"); return 1
    if args.cmd == "replay":
        return cmd_replay(args, cfg)
    if args.cmd == "apply-plan":
        from .app import build_app
        app = build_app(cfg)
        for line in app.organizer.apply(Path(args.plan)):
            print(" •", line)
        return 0
    if args.cmd == "search":
        from .app import build_app
        app = build_app(cfg)
        print(app.query.answer(args.query))
        return 0
    if args.cmd == "pair":
        resp = send(cfg, {"cmd": "pair"})
        if not resp.get("ok"):
            print(f"❌ {resp.get('error', 'daemon not reachable')}\n"
                  "   Is the daemon running? systemctl --user start voice-brain")
            return 1
        pin = resp["pin"]
        print()
        print("╔══════════════════════════════╗")
        print("║   Voice Brain — phone pairing ║")
        print("╚══════════════════════════════╝")
        print()
        print(f"    On your phone, in the Voice Brain Capture app:")
        print(f"    1. tap \"Scan for laptop\"")
        print(f"    2. tap \"Pair with laptop\"")
        print(f"    3. enter this PIN:")
        print()
        print(f"          ┌─┐ ┌─┐ ┌─┐ ┌─┐ ┌─┐ ┌─┐")
        print(f"          │{pin[0]}│ │{pin[1]}│ │{pin[2]}│ │{pin[3]}│ │{pin[4]}│ │{pin[5]}│")
        print(f"          └─┘ └─┘ └─┘ └─┘ └─┘ └─┘")
        print()
        print(f"    (valid for {resp.get('expires_in', 600) // 60} minutes)")
        return 0
    return 1


def cmd_daemon(cfg) -> int:
    from .app import build_app
    from .daemon import Daemon
    from .ui import make_ui
    app = build_app(cfg)
    app.vault.ensure_folders()
    ui = make_ui(cfg)
    daemon = Daemon(app, ui)
    server = __import__("threading").Thread(target=daemon._serve_forever, daemon=True)
    server.start()
    print(f"voice-brain daemon up — socket {cfg.socket_path}")
    if str(cfg.get("daemon.mode", "relay")) == "standalone":
        from .http_api import CaptureAPI
        api = CaptureAPI(daemon,
                         str(cfg.get("daemon.listen_host", "127.0.0.1")),
                         int(cfg.get("daemon.listen_port", 47799)),
                         str(cfg.get("daemon.token", "")))
        try:
            api.start()
            print(f"standalone capture API on {api.url} (phone-ready)")
            if str(cfg.get("daemon.listen_host", "127.0.0.1")) not in ("127.0.0.1", "localhost"):
                from .discovery import DiscoveryResponder
                DiscoveryResponder(int(cfg.get("daemon.listen_port", 47799)),
                                   str(cfg.get("daemon.listen_host", "0.0.0.0"))).start()
                print("LAN discovery responder on UDP :47798 (phone: tap 'Scan')")
        except OSError as exc:
            print(f"⚠️ capture API failed to bind {api.url}: {exc}")
    try:
        ui.run()  # blocks (GTK loop, or sleep loop in notify mode)
    except KeyboardInterrupt:
        daemon._shutdown.set()
        print("\nshutting down…")
    return 0


def _print(resp: dict) -> int:
    print(json.dumps(resp, indent=1, ensure_ascii=False))
    return 0 if resp.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
