"""Hands-free audio capture: arm -> VAD start -> VAD stop.

``parec`` (PipeWire pulse-compat, already installed) negotiates remix/resample of the
3-channel s24-32le T2 mic down to mono 16 kHz s16le, and streams raw PCM to stdout.
A reader thread computes RMS on 20 ms frames for the start/stop gates and keeps a
0.5 s pre-roll ring buffer so the first word is never clipped.

States: ARMED -> RECORDING -> FINALIZED (or ARM_TIMEOUT / CANCELLED).
Final output: 16 kHz mono WAV in the spool dir (stdlib ``wave``).
"""

from __future__ import annotations

import queue
import shutil
import signal
import struct
import subprocess
import threading
import time
import wave
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

FRAME_MS = 20


class CaptureState(Enum):
    ARMED = "armed"
    RECORDING = "recording"
    DONE = "done"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class CaptureResult:
    state: CaptureState
    wav_path: Path | None = None
    duration_s: float = 0.0


class CaptureError(RuntimeError):
    pass


def resolve_source(cfg) -> str | None:
    """Resolve the pactl source name for capture ('default' -> default source)."""
    configured = str(cfg.get("audio.source", "default"))
    if configured and configured != "default":
        return configured
    try:
        out = subprocess.run(["pactl", "get-default-source"], capture_output=True,
                             text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def source_is_muted(source: str | None) -> bool:
    """The OS mute is the privacy kill-switch — Voice Brain must honor it."""
    try:
        out = subprocess.run(["pactl", "get-source-mute", source or "@DEFAULT_SOURCE@"],
                             capture_output=True, text=True, timeout=5)
        return out.returncode == 0 and out.stdout.strip().lower() == "true"
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


class MicCapture:
    """One capture session per arm. Not reusable after finalize — build a new one."""

    def __init__(self, cfg, on_state: Callable[[str], None] | None = None,
                 on_level: Callable[[float], None] | None = None):
        self.cfg = cfg
        self.on_state = on_state or (lambda s: None)
        self.on_level = on_level or (lambda v: None)

        self.sample_rate: int = int(cfg.get("audio.sample_rate", 16000))
        self.rms_threshold: float = float(cfg.get("audio.vad_start_rms", 0.02))
        start_ms: int = int(cfg.get("audio.vad_start_min_speech_ms", 120))
        self.start_frames: int = max(1, start_ms // FRAME_MS)
        silence_ms: int = int(cfg.get("audio.silence_stop_ms", 1200))
        self.silence_frames: int = max(1, silence_ms // FRAME_MS)
        self.arm_timeout_s: float = float(cfg.get("audio.arm_timeout_s", 15))
        self.max_recording_s: float = float(cfg.get("audio.max_recording_s", 90))
        preroll_s: float = float(cfg.get("audio.preroll_s", 0.5))
        self.preroll_frames: int = max(1, int(preroll_s * 1000 / FRAME_MS))

        self.frame_bytes: int = self.sample_rate * 2 * FRAME_MS // 1000  # s16le mono
        self.bytes_per_sample = 2

        # Noise-adaptive VAD: learn the ambient floor and only count energy
        # ABOVE it as speech — background noise then can't block the silence
        # auto-stop (or trigger false starts).
        self.noise_floor: float | None = None

        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._result_q: queue.Queue[CaptureResult] = queue.Queue(maxsize=1)
        self._cancel = threading.Event()
        self._force_done = threading.Event()
        self._state = CaptureState.ARMED
        self._preroll: list[bytes] = []
        self._buffer: list[bytes] = []
        self._recorded_s: float = 0.0
        self._armed_since: float = time.time()

    # ------------------------------------------------------------------ lifecycle

    def arm(self) -> None:
        source = resolve_source(self.cfg)
        if source and self.cfg.get("safety.respect_source_mute", True) and source_is_muted(source):
            raise CaptureError("Microphone is muted — Voice Brain will not capture. Unmute to use voice.")

        if shutil.which("parec"):
            cmd = ["parec", "--raw",
                   "--format=s16le", f"--rate={self.sample_rate}", "--channels=1"]
            if source:
                cmd.append(f"--device={source}")
        elif shutil.which("pw-record"):
            cmd = ["pw-record", "--raw", "--format", "s16",
                   "--rate", str(self.sample_rate), "--channels", "1"]
            if source:
                cmd += ["--target", source]
        else:
            raise CaptureError("No capture binary found (need parec or pw-record).")

        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL)
        # Give the capture a moment to fail loudly (bad device negotiation etc.)
        time.sleep(0.15)
        if self._proc.poll() not in (None,):
            raise CaptureError(f"Capture process died at startup (rc={self._proc.returncode}). Check audio.source in config.")

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._set_state(CaptureState.ARMED)

    def cancel(self) -> None:
        self._cancel.set()
        self._stop_proc()

    def finalize_now(self) -> None:
        """Force end of recording; whatever was captured gets processed (toggle press)."""
        self._force_done.set()

    def result(self, timeout: float | None = None) -> CaptureResult:
        """Block until finalized. Returns DONE/TIMEOUT/CANCELLED result."""
        res = self._result_q.get(timeout=timeout or (self.arm_timeout_s + self.max_recording_s + 5))
        return res

    # ------------------------------------------------------------------ internals

    def _set_state(self, state: CaptureState) -> None:
        self._state = state
        self.on_state(state.value)

    def _stop_proc(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.send_signal(signal.SIGTERM)
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass

    def _finalize(self, state: CaptureState) -> None:
        if self._state in (CaptureState.DONE, CaptureState.CANCELLED, CaptureState.TIMEOUT):
            return
        self._stop_proc()
        wav_path = None
        duration = self._recorded_s
        if state == CaptureState.DONE and self._buffer:
            wav_path = self._write_wav(self._buffer)
        self._set_state(state)
        self._result_q.put(CaptureResult(state=state, wav_path=wav_path, duration_s=duration))

    def _write_wav(self, frames: list[bytes]) -> Path:
        spool = self.cfg.spool_dir()
        spool.mkdir(parents=True, exist_ok=True)
        path = spool / f"capture-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time()*1000)%1000:03d}.wav"
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            for frame in frames:
                wf.writeframes(frame)
        return path

    def _effective_threshold(self) -> float:
        if self.noise_floor is None:
            return self.rms_threshold
        return max(self.rms_threshold, self.noise_floor * 1.6 + 0.003)

    def _learn_floor(self, rms: float) -> None:
        self.noise_floor = rms if self.noise_floor is None else 0.9 * self.noise_floor + 0.1 * rms

    def _rms(self, frame: bytes) -> float:
        n = len(frame) // self.bytes_per_sample
        if n == 0:
            return 0.0
        samples = struct.unpack(f"<{n}h", frame[:n * 2])
        acc = 0
        for s in samples:
            acc += s * s
        return (acc / n) ** 0.5 / 32768.0

    def _loop(self) -> None:
        assert self._proc and self._proc.stdout
        stream = self._proc.stdout
        loud_streak = 0
        quiet_streak = 0
        try:
            while not self._cancel.is_set():
                if self._force_done.is_set():
                    self._finalize(CaptureState.DONE if self._state == CaptureState.RECORDING
                                   else CaptureState.TIMEOUT)
                    return
                frame = stream.read(self.frame_bytes)
                if not frame:
                    # source closed (device unplugged / process killed)
                    if self._state == CaptureState.RECORDING:
                        self._finalize(CaptureState.DONE)
                    elif self._state == CaptureState.ARMED:
                        self._finalize(CaptureState.TIMEOUT)
                    return

                rms = self._rms(frame)
                self.on_level(min(1.0, rms * 4))  # scale for the level meter
                loud = rms >= self._effective_threshold()
                if not loud:
                    self._learn_floor(rms)  # ambient (incl. steady noise) becomes the floor

                if self._state == CaptureState.ARMED:
                    self._preroll.append(frame)
                    if len(self._preroll) > self.preroll_frames:
                        self._preroll.pop(0)
                    if loud:
                        loud_streak += 1
                        if loud_streak >= self.start_frames:
                            # speech! begin recording, prepending the pre-roll
                            self._buffer = list(self._preroll)
                            self._recorded_s = (self.preroll_frames + loud_streak) * FRAME_MS / 1000
                            self._set_state(CaptureState.RECORDING)
                    else:
                        loud_streak = 0
                        if time.time() - self._armed_since > self.arm_timeout_s:
                            self._finalize(CaptureState.TIMEOUT)
                            return

                elif self._state == CaptureState.RECORDING:
                    self._buffer.append(frame)
                    self._recorded_s += FRAME_MS / 1000
                    if loud:
                        quiet_streak = 0
                    else:
                        quiet_streak += 1
                        if quiet_streak >= self.silence_frames:
                            self._finalize(CaptureState.DONE)
                            return
                    if self._recorded_s >= self.max_recording_s:
                        self._finalize(CaptureState.DONE)
                        return
        finally:
            if self._cancel.is_set() and self._state not in (CaptureState.DONE,
                                                             CaptureState.TIMEOUT):
                self._finalize(CaptureState.CANCELLED)
