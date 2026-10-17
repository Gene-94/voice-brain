"""libnotify wrapper. All user-facing results flow through here."""

from __future__ import annotations

import shutil
import subprocess

APP = "Voice Brain"


def notify(title: str, body: str = "", *, urgency: str = "normal", timeout_ms: int = 6000,
           actions: list[tuple[str, str]] | None = None) -> None:
    """Best-effort notification. Never raises. `actions` only work on action-capable daemons."""
    if not shutil.which("notify-send"):
        print(f"[{APP}] {title}\n{body}")
        return
    cmd: list[str] = ["notify-send", "-a", APP, "-u", urgency, "-t", str(timeout_ms)]
    for action_key, label in actions or []:
        cmd += ["-A", f"{action_key}={label}"]
    cmd += [title]
    if body:
        cmd += [body]
    try:
        subprocess.run(cmd, check=False, timeout=15,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def notify_result(title: str, body: str) -> None:
    """Green-flash result notification."""
    notify(title, body, urgency="normal", timeout_ms=6000)


def notify_error(title: str, body: str) -> None:
    notify(f"❌ {title}", body, urgency="critical", timeout_ms=10000)
