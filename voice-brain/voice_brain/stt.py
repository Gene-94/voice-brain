"""whisper.cpp integration (whisper-cli subprocess). No pip audio stack — see plan §0/§3."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

WHISPER_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{model}.bin"
_LOGPROB_RE = re.compile(r"avg_logprob\s*=\s*(-?\d+\.?\d*)")


class STTUnavailable(RuntimeError):
    pass


@dataclass
class Transcription:
    text: str
    avg_logprob: float | None = None

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


class WhisperSTT:
    def __init__(self, cfg):
        self.cfg = cfg
        self.model_name: str = cfg.get("stt.model", "base.en")
        self.language: str = cfg.get("stt.language", "en")
        self.beam_size: int = int(cfg.get("stt.beam_size", 5))

    # ------------------------------------------------------------ availability

    @staticmethod
    def cli_available() -> bool:
        return bool(shutil.which("whisper-cli"))

    def model_path(self) -> Path:
        return self.cfg.models_dir() / f"ggml-{self.model_name}.bin"

    def model_present(self) -> bool:
        p = self.model_path()
        return p.exists() and p.stat().st_size > 1_000_000

    def ensure_model(self, force: bool = False) -> bool:
        """Download the GGML model if missing. Returns True if present afterwards."""
        if self.model_present() and not force:
            return True
        dest = self.model_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = WHISPER_URL.format(model=self.model_name)
        tmp = dest.with_suffix(".part")
        try:
            urllib.request.urlretrieve(url, tmp)  # noqa: S310 — fixed trusted host
            os.replace(tmp, dest)
            return True
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            raise STTUnavailable(f"Failed to download whisper model {self.model_name}: {exc}") from exc

    # ------------------------------------------------------------ transcription

    def decode_to_wav(self, audio: Path) -> Path:
        """Convert any phone/browser codec (m4a/opus/webm/aac) to 16k mono WAV via ffmpeg."""
        if audio.suffix == ".wav":
            return audio
        if not shutil.which("ffmpeg"):
            raise STTUnavailable("ffmpeg not found — needed to decode phone audio")
        out = audio.with_suffix(audio.suffix + ".vb.wav")
        subprocess.run(["ffmpeg", "-y", "-i", str(audio), "-ac", "1", "-ar", "16000",
                        "-sample_fmt", "s16", str(out)],
                       capture_output=True, timeout=120, check=True)
        return out

    def transcribe_file(self, audio: Path, initial_prompt: str | None = None) -> Transcription:
        """Transcribe any audio file (decodes to WAV first if needed)."""
        wav = self.decode_to_wav(Path(audio))
        return self.transcribe(wav, initial_prompt)

    def transcribe(self, wav: Path, initial_prompt: str | None = None) -> Transcription:
        if not self.cli_available():
            raise STTUnavailable(
                "whisper-cli not found. Install it with: sudo pacman -S whisper-cpp"
            )
        # re-read per call: language/model can be changed live from the plugin
        # (Voice Brain Settings/settings.md — the daemon hot-reloads it)
        self.model_name = str(self.cfg.get("stt.model", self.model_name))
        self.language = str(self.cfg.get("stt.language", self.language))
        if not self.model_present():
            self.ensure_model()

        wav = Path(wav)
        out_base = wav.with_suffix("")
        cmd: list[str] = [
            "whisper-cli",
            "-m", str(self.model_path()),
            "-f", str(wav),
            "-bs", str(self.beam_size),
            "-oj", "-of", str(out_base),
            "-np",
        ]
        if self.language and self.language != "auto":
            cmd += ["-l", self.language]
        if initial_prompt and self.language and self.language != "auto":
            # --prompt biases decoding toward vault vocabulary (names, projects,
            # tech terms). ONLY with a pinned language: whisper's prompt tokens
            # carry language, so an English "Vocabulary: …" prompt under auto
            # detection makes whisper TRANSLATE foreign speech into English.
            cmd += ["--prompt", initial_prompt[:400]]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise STTUnavailable(f"whisper-cli failed: {proc.stderr[:400]}")

        logprob = None
        m = _LOGPROB_RE.search(proc.stdout)
        if m:
            logprob = float(m.group(1))

        # Prefer JSON output (segments), fall back to parsing stdout.
        json_path = Path(str(out_base) + ".json")
        text = ""
        if json_path.exists():
            try:
                doc = json.loads(json_path.read_text())
                segments = doc.get("transcription") or []
                text = " ".join(s.get("text", "").strip() for s in segments).strip()
            except (json.JSONDecodeError, OSError):
                text = ""
        if not text:
            # whisper-cli prints recognized text lines to stdout when -otxt is absent
            lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
            text = " ".join(lines).strip()

        text = re.sub(r"\s+", " ", text).strip()
        return Transcription(text=text, avg_logprob=logprob)
