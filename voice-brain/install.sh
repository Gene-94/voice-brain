#!/usr/bin/env bash
# Voice Brain — one-shot installer. Run WITHOUT sudo (it asks only for pacman).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

echo "==> [1/6] System package: whisper-cpp (STT + silero VAD)"
if ! command -v whisper-cli >/dev/null; then
  echo "    sudo needed for pacman:"
  sudo pacman -S --needed whisper-cpp || \
    echo "    ⚠️ skipped — run 'sudo pacman -S whisper-cpp' later; STT needs it."
fi

echo "==> [2/6] Python project via uv"
command -v uv >/dev/null || { echo "uv not found — install: https://docs.astral.sh/uv/" >&2; exit 1; }
cd "$PROJECT_DIR"
uv sync
uv run voice-brain --version

echo "==> [3/6] Ollama models (gemma3:4b quick lane, gemma4:latest deep lane)"
ollama pull gemma3:4b
ollama pull gemma4:latest

echo "==> [4/6] Whisper model + vault folders"
uv run voice-brain doctor --setup || echo "  ⚠️ doctor reported issues above — continuing (non-fatal)"

echo "==> [5/6] systemd user units (daemon + nightly stats timer)"
mkdir -p "$SYSTEMD_DIR"
for unit in voice-brain.service voice-brain-stats.service voice-brain-stats.timer; do
  cp "$PROJECT_DIR/systemd/$unit" "$SYSTEMD_DIR/"
done
# point the service at the project's venv binary
sed -i "s|%h/.local/bin/voice-brain|$PROJECT_DIR/.venv/bin/voice-brain|g" \
  "$SYSTEMD_DIR/voice-brain.service" "$SYSTEMD_DIR/voice-brain-stats.service"
systemctl --user daemon-reload
systemctl --user enable --now voice-brain.service voice-brain-stats.timer

echo "==> [6/6] Hyprland keybinding"
HYPR_CONF="${XDG_CONFIG_HOME:-$HOME/.config}/hypr"
if [ -d "$HYPR_CONF" ] && ! grep -rqs "voice-brain toggle" "$HYPR_CONF"; then
  cat <<'EOF'

  Add this line to your Hyprland config (e.g. ~/.config/hypr/bindings.conf):

    bind = SUPER ALT, V, exec, voice-brain toggle

EOF
fi

echo
echo "✅ Done. Next: 'voice-brain doctor' should show all ✅."
echo "Press SUPER+ALT+V and talk to your brain."
