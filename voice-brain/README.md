# Voice Brain 🧠🎙️

> Local, voice-first knowledge assistant for your Obsidian vault.
> Speak → Whisper transcribes → Gemma reasons → Markdown written. Zero cloud.

Press **SUPER+ALT+V**, speak naturally, go silent. Voice-activity detection starts and
stops recording for you. Your dreams, journal, notes and a quantified-self JSON dataset
build themselves — no subscriptions, no API keys, no telemetry, nothing leaves your machine.

## What it does

| Say | What happens |
|---|---|
| *"I had a dream where I was flying over a neon city… then another dream about…"* | One Markdown file **per dream** in `Dream Journal/` — evocative titles, themes, vividness, frontmatter |
| *"log this: great workout, mood is 8 out of 10"* | Timestamped append to `Journal/YYYY-MM-DD.md` + implicit stat tags |
| *"create a note on Rust async patterns"* | LLM-drafted note in `Voice Brain Inbox/` |
| *"what do I know about networking?"* | Answer from your vault with `[[wikilink]]` citations |
| *"generate stats"* / nightly at 23:59 | Quantified-self JSON in `Stats/YYYY-MM-DD.json` (sleep, mood, energy, nutrition, creative output, correlations…) |
| *"brief me"* | Morning briefing: yesterday's readiness, top recommendation, open TODOs |
| *"scratch that"* | Undo the last thing Voice Brain wrote |
| anything else | Verbatim capture to the inbox — **nothing you say is ever lost** |

## Stack

whisper.cpp (STT, silero VAD trimming) · Ollama (gemma3:4b fast lane, gemma4:latest deep lane)
· Python 3.14 + uv · PipeWire (`parec` capture) · GTK4 layer-shell status pill · systemd user units

## Install (Omarchy / Arch)

```bash
git clone <this repo> && cd voice-brain
./install.sh
```

What it does: installs `whisper-cpp`, pulls gemma models, downloads the whisper model,
creates the managed vault folders, enables `voice-brain.service` + the 23:59 stats timer.
Add `bind = SUPER ALT, V, exec, voice-brain toggle` to your Hyprland config.

## Hands-free capture model

```
IDLE ──toggle──▶ ARMED ──speech detected──▶ RECORDING ──1.2 s silence──▶ FINALIZE
       (15 s arm timeout)                                    (90 s hard cap)
FINALIZE ──▶ whisper.cpp ──▶ trigger router ──▶ Gemma ──▶ vault write ──▶ notify
```

- 0.5 s pre-roll ring buffer — the first word is never clipped
- vault-glossary `--prompt` biasing: your project names stop garbling
- every utterance archived (JSONL) and every audio file spooled for 7 days

## Design principles

1. **Nothing is ever lost** — capture-everything inbox fallback, audio spool, undo ledger.
2. **The LLM narrates, code calculates** — correlations/streaks/deltas are computed
   deterministically; Gemma only interprets pre-computed numbers.
3. **Loud errors beat silent truncation** — every Ollama call sets `num_ctx` explicitly
   and refuses to send prompts that would overflow context.
4. **Safe-by-construction vault ops** — atomic writes, append-only journal, destructive
   organization requires an explicitly applied plan file, git snapshots if your vault has a repo.
5. **Minimal UI** — a small GTK pill (or notify-only headless mode). No server, no web UI.

## Commands

```
voice-brain doctor [--mic] [--setup]   # environment check; --mic calibrates VAD threshold
voice-brain daemon                     # background service (owns mic + overlay)
voice-brain toggle                     # bind to SUPER+ALT+V
voice-brain say "log this: testing"    # pipeline without a mic
voice-brain replay cap.wav [--route]   # re-run spooled audio
voice-brain generate-stats [--date D]  # same path as the nightly timer
voice-brain brief / undo / status / search "query"
```

## Configuration

`~/.config/voice-brain/config.yaml` (see `voice_brain/config.py` for all defaults).
Honors the OS mic mute as a privacy kill-switch. `.voice-brain-ignore` in the vault
excludes private notes from indexing, queries and stats.

## Privacy

The only network call in the codebase is to `localhost:11434` (your own Ollama).
All audio, transcripts and stats stay on disk under `~/.local/state/voice-brain/` and
inside your vault. No telemetry. Ever.

MIT licensed. Talk to your brain. Understand yourself.
