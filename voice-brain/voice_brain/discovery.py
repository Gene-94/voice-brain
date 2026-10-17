"""LAN discovery: the phone broadcasts "VB_DISCOVER" on UDP :47798 and this
responder answers with host + port + name — no hardcoded IPs, no mDNS deps.
Runs only when the capture API is bound beyond localhost."""

from __future__ import annotations

import json
import socket
import threading

MAGIC = b"VB_DISCOVER"
DISCOVERY_PORT = 47798


class DiscoveryResponder:
    def __init__(self, service_port: int, host: str = "0.0.0.0",
                 listen_port: int = DISCOVERY_PORT):
        self.service_port = service_port
        self.host = host
        self.listen_port = listen_port
        self._sock: socket.socket | None = None

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.bind((self.host, self.listen_port))
        except OSError:
            return  # discovery is best-effort; never block the daemon
        self._sock = sock
        threading.Thread(target=self._serve, daemon=True,
                         name="vb-discovery").start()

    def _serve(self) -> None:
        assert self._sock
        payload = json.dumps({
            "service": "voice-brain",
            "proto": 1,
            "name": socket.gethostname(),
            "port": self.service_port,
        }).encode()
        while True:
            try:
                data, addr = self._sock.recvfrom(256)
                if data.strip().startswith(MAGIC):
                    self._sock.sendto(payload, addr)
            except OSError:
                return
