"""Thin unix-socket client used by the CLI (toggle/cancel/status/say)."""

from __future__ import annotations

import json
import socket


def send(cfg, cmd: dict, timeout: float = 5.0) -> dict:
    path = str(cfg.socket_path)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(path)
        sock.sendall(json.dumps(cmd).encode() + b"\n")
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if data.endswith(b"\n"):
                break
        return json.loads(data.decode() or "{}")
    except (FileNotFoundError, ConnectionRefusedError):
        return {"ok": False, "error": "Voice Brain daemon is not running "
                                      "(start with: voice-brain daemon)"}
    except (socket.timeout, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        sock.close()
