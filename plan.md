# Voice Brain — Technical Implementation Plan

> Local, voice-first knowledge assistant for your Obsidian vault.
> Speak → Whisper transcribes → Gemma reasons → Markdown written. Zero cloud.

**Status:** Planning v1.0 · **Source spec:** `voice_brain.md` · **Hardware:** MacBook Pro 16" 2019 (T2), i7-9750H, 32 GB RAM, no CUDA

---

## 0. Findings from the actual machine (decisions are grounded in this)

An audit of your system changes several spec assumptions:

| Discovery | Impact on plan |
|---|---|
| Ollama is running at `localhost:11434`, but **no models are pulled** | Setup must `ollama pull gemma3:4b` + `gemma4:latest` and pin exact model tags in config |
| **Python 3.14** is the system Python | `faster-whisper`/`ctranslate2` wheels will lag behind 3.14 for months. **We drop the `faster-whisper` pip dependency entirely.** |
| **`whisper-cpp` 1.9.3 is in the official Arch repos** (`extra/whisper-cpp`, deps: ffmpeg + ggml) | Use whisper.cpp binaries via subprocess. Ships `whisper-cli` (STT) and `whisper-vad`/`--vad` flag (silero VAD). No pip audio-stack hell, native speed. |
| `pw-record` / `parec` / `ffmpeg` / `arecord` all present (PipeWire) | Audio capture via `pw-record` subprocess — no `sounddevice`/PortAudio needed |
| **`gtk4-layer-shell` 1.3.0 already installed** | The "minimal visual interface" is a tiny GTK4 layer-shell status pill — native Wayland, floats over everything, ~150 lines |
| **`cronie` is inactive** | Nightly stats auto-generation uses a **systemd user timer** instead of cron |
| Vault exists at `~/Documents/Obsidian/Omarchy-Yev` with existing folders incl. `Dream Journal/`, plus **Portuguese filenames** | STT language must be configurable (`en` default, `pt`/`auto` supported); LLM prompts must instruct output-language matching |
| Mic = **Apple T2 internal digital mic** (`alsa_input.pci-0000_04_00.3.HiFi__Mic__source`), 3-channel s24-32le @48kHz | `pw-record` writes a WAV natively and auto-negotiates the source format — then `ffmpeg -ac 1 -ar 16000` downmix before whisper.cpp. No manual raw-format handling. |
| **No Vulkan driver installed** (`vulkan-radeon` absent, no `vulkaninfo`) | whisper.cpp runs **CPU-only** — fine, base/small models are fast on this CPU. GPU offload is a later optional experiment, not a plan assumption |
| Swap = 31.2G zram + 31.2G swapfile (matches device_specs' 62G) | 9b inference can page under memory pressure without OOM — safety net only |
| dGPU VRAM confirmed **4 GB** (base config) | Too small to be a meaningful LLM offload target; ignore the dGPU for inference entirely |
| `notify-send`, `hyprctl`, Hyprland 0.56.2 available | OSD feedback via `notify-send`; keybinding via Hyprland `bind` |

---

## 1. Product Summary

**Voice Brain** is a hands-free, fully-local voice assistant layered on top of your existing Obsidian vault:

1. **Activate** with a single keypress (`SUPER+ALT+V`) — this *arms* the listener.
2. **Voice-activity detection starts and stops recording for you.** Begin speaking → recording starts on first detected speech. Stop speaking → after a configurable silence window (~1.2s) the recording auto-finalizes. No key-holding, no "click to stop."
3. **Whisper** (whisper.cpp, local) transcribes.
4. **Trigger router** detects intent from phrase prefixes (`"I had a dream…"`, `"log this…"`, `"generate stats"`, …), falling through to a general command handler.
5. **Gemma** via Ollama does the reasoning (dream splitting, note drafting, vault Q&A, stats extraction).
6. Files are written directly into the vault; a **minimal GTK overlay pill** + `notify-send` show state and results.

Four managed folders in the vault (auto-created, marked with `.voice-brain-generated`):
`Dream Journal/`, `Journal/`, `Stats/`, `Voice Brain Inbox/` (default landing spot for general captures, avoids polluting your existing folders).

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ USER LAYER                                                          │
│  [SUPER+ALT+V] arm → speak → silence → auto-stop                     │
└──────────────┬──────────────────────────────────────────────────────┘
               │ (hyprland bind → voice-brain toggle via unix socket)
┌──────────────▼──────────────────────────────────────────────────────┐
│ voice-braind (Python daemon, systemd user service)                  │
│                                                                     │
│  ┌───────────────┐    ┌────────────────┐    ┌────────────────────┐  │
│  │ capture.py    │    │ stt.py         │    │ intent.py          │  │
│  │ pw-record →   │───▶│ whisper-cli    │───▶│ phrase triggers     │  │
│  │ ffmpeg downmix│    │ (local, int8)  │    │ (regex) → fallback  │  │
│  │ + VAD gate    │    └────────────────┘    │ LLM intent classify│  │
│  └───────────────┘                         └───────┬────────────┘  │
│                                                    │               │
│  ┌────────────────────────────────────────────────▼─────────────┐  │
│  │ ROUTERS: dream_journal · daily_journal · stats · notes ·     │  │
│  │ query · organize                                              │  │
│  └──────┬──────────────────────────────────┬───────────────────┘  │
│         │                                  │                      │
│  ┌──────▼───────────┐              ┌───────▼───────────────────┐  │
│  │ llm.py           │              │ vault.py                    │  │
│  │ Ollama HTTP      │              │ FS ops, folder mgmt, scan,  │  │
│  │ gemma3:4b (fast) │              │ frontmatter read/write,     │  │
│  │ gemma4:latest (deep) │              │ journal append, safe writes │  │
│  └──────────────────┘              └────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ ui.py → GTK4 layer-shell overlay pill + notify-send results   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
               │                                    │
┌──────────────▼──────────────┐   ┌────────────────▼─────────────────┐
│ Ollama (localhost:11434)     │   │ Obsidian Vault (filesystem)      │
│ gemma3:4b · gemma4:latest        │   │ ~/Documents/Obsidian/Omarchy-Yev │
└─────────────────────────────┘   └──────────────────────────────────┘

Nightly: systemd user timer → voice-brain --generate-stats --date today
```

---

## 3. Tech Stack (final decisions)

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.14 (system) + **uv** project | Already installed; uv gives locked, reproducible venv. Backend logic is I/O-bound; speed lives in whisper.cpp/Ollama anyway. |
| STT | **whisper.cpp** (`pacman -S whisper-cpp`), `whisper-cli` subprocess | Native GGML CPU path, no pip wheels needed on py3.14, works perfectly on i7-9750H, ships silero VAD. |
| Whisper model | `base.en` → upgrade path `small` / `small.en` | ~100–300 ms latency on this CPU. Download GGML models once into `~/.local/share/voice-brain/models/`. |
| VAD | **Silero VAD** via whisper.cpp (`--vad` on `whisper-cli` / `whisper-vad` tool) + a light Python-side RMS energy gate for arm/stop decisions | Two-tier: cheap RMS gate decides record start/stop (fast, low latency); silero confirms and trims on finalization. |
| Audio capture | `pw-record` (or `parec`) → `ffmpeg` downmix → 16 kHz mono s16le WAV | All binaries already present. Handles the 3-channel mic correctly (`-ac 1`). |
| LLM | **Ollama HTTP API** (`http://localhost:11434`) — `ollama` python pkg or plain `requests` | Already served. `gemma3:4b` for fast tasks (dream split, titles, intent fallback), `gemma4:latest` for deep tasks (stats, vault queries, creativity assessment). `keep_alive: "30m"` so the model stays warm; `format: "json"` for schema-tight outputs. |
| Vault format | Plain Markdown + YAML frontmatter (stdlib yaml via `PyYAML`) | Obsidian-native. All writes atomic (`tempfile` + `os.replace`) so Obsidian picks them up live. |
| UI | **GTK4 + gtk4-layer-shell overlay pill** (~400×72 px, corner-anchored) + `notify-send` for results | You already have the library. Pill shows state: 🎙️ pulsing while armed/recording (with a live input-level meter), 🧠 spinner while transcribing/thinking, ✅/❌ result flash. Disappears after 4 s idle. Genuinely minimal. |
| Notifications | `notify-send` (libnotify) | Omarchy-native OSD. |
| Scheduling | systemd **user timer** `voice-brain-stats.timer` (23:59 daily) | cronie is inactive on your machine; systemd user units also solve autostart (`voice-brain.service` WantedBy `graphical-session.target`). |
| IPC | Unix domain socket at `$XDG_RUNTIME_DIR/voice-brain.sock` | The Hyprland bind runs `voice-brain toggle` → tiny client sends `TOGGLE` to daemon. Single daemon owns mic + overlay, avoids double-capture races. |
| Config | `~/.config/voice-brain/config.yaml` + `--config` override | See §8. |
| Validation | `pydantic` (v2) for stats schema + note frontmatter models | Py3.14 wheels for pydantic-core are available; if not, fall back to `jsonschema` (pure python-friendly). |

### Models to pull during setup

```bash
ollama pull gemma3:4b      # fast lane: dream splitting, titles, intent classification
ollama pull gemma4:latest      # deep lane: stats, queries, creativity assessment
# GGML whisper models (whisper.cpp auto-downloads on first run, or prefetch):
whisper-cli --model base.en -f test.wav   # auto-fetches ggml-base.en.bin
```

Model tags are **pinned in config** so behavior is reproducible.

---

## 4. The Hands-Free Voice Loop (core UX)

Your key requirement: **recording starts and stops on voice detection.** This replaces the spec's hold-to-talk model with a superior *arm → auto-capture* state machine:

```
IDLE ──(keybind / socket TOGGLE)──▶ ARMED
ARMED ──(RMS energy > threshold for ≥120 ms)──▶ RECORDING
ARMED ──(15 s with no speech)──▶ ARM_TIMEOUT → IDLE ("Nothing heard" toast)
RECORDING ──(silence ≥ 1.2 s after ≥1 speech segment)──▶ FINALIZING
RECORDING ──(hard cap 90 s)──▶ FINALIZING
RECORDING ──(keybind pressed again)──▶ FINALIZING (manual override, flush now)
FINALIZING ──(trim edges w/ silero VAD → whisper-cli)──▶ TRANSCRIBING
TRANSCRIBING ──▶ ROUTING (trigger match) ──▶ PROCESSING (Ollama)
PROCESSING ──▶ WRITING (vault) ──▶ notify + pill flash ──▶ IDLE
PROCESSING ──(LLM/parse error)──▶ notify error ──▶ IDLE (audio kept in spool for retry)
```

### Implementation details

- **Capture**: `pw-record --target <source> <tmp.wav>` — PipeWire auto-negotiates the source's native spec (3ch s24-32le on the T2 mic) and writes a WAV directly, so we never hand-manage raw sample formats. A background reader thread tails the stream to compute RMS on 20 ms frames for the gates. On finalize: `ffmpeg -i tmp.wav -ac 1 -ar 16000 -sample_fmt s16 out.wav`, then trim with whisper.cpp's VAD (`--vad --vad-min-silence-ms`) before decoding.
- **Tunables in config**: `arm_timeout_s: 15`, `vad_start_rms: 0.02`, `vad_start_min_speech_ms: 120`, `silence_stop_ms: 1200`, `max_recording_s: 90`.
- **Spool**: every finalized WAV is kept in `~/.local/state/voice-brain/spool/` for 7 days — if the pipeline crashes or you hit an error, the utterance is recoverable, and re-processing is possible (`voice-brain replay <file>`).
- **Instant feedback**: pill turns red-pulse the moment speech is detected, so you *know* the capture started.
- **Dream Re-entry mode** (from spec): config flag `dream.defer_processing` — dream-trigger captures can be written as a raw narration stub instantly and enriched by Gemma later, so you can fall back asleep mid-sentence and the file still exists.

---

## 5. Trigger Routing & LLM Interaction

### 5.1 Phrase triggers (regex, priority order)

```python
TRIGGERS = [
    ("dream",    r"^\s*(i (had|just had) a dream|i dream(ed|t) about|in my dream|last night i dreamt|there was this dream)\b"),
    ("stats",    r"^\s*(generate|make|create) stats?\b|^\s*how was my day\b|^\s*analyze my week\b"),
    ("brief",    r"^\s*brief me\b"),
    ("stat_log", r"^\s*(log|track) (a )?stat\b"),
    ("journal",  r"^\s*(log (this|that)|journal this|remember this)\b"),
    # no match → general
]
```

- Priority rule from spec preserved: dream prefix wins over journal if both appear.
- If no phrase matches, a **cheap LLM intent classification** (gemma3:4b, `format: json`, ~1 s) picks: `create_note | query | organize | chat` — this lets you say *"hey can you draft a note about rust error handling"* without memorizing commands.
- Fallback of the fallback: unrecognized → saved verbatim to `Voice Brain Inbox/` as a capture with a toast: *"Didn't understand — saved to inbox"*. **Nothing you say is ever lost.**

### 5.2 LLM call discipline (all calls through `llm.py`)

- Two lanes: `quick` (gemma3:4b, temp 0.4) and `deep` (gemma4:latest, temp 0.3).
- All structured outputs requested with `format: "json"` (Ollama constrains decoding to valid JSON) **plus** a pydantic validation pass **plus** one repair retry (`"This JSON failed schema: {errors}. Return corrected JSON only."`). Never trust an LLM's first JSON.
- System prompt suffix on every call: *"Respond in the same language the user spoke."* (your vault is bilingual EN/PT).
- `keep_alive: "30m"` so the model stays resident between quick captures.
- **Every call sets `options.num_ctx` explicitly.** Ollama's default context is ~4096–8192 tokens and it *silently truncates* longer prompts — the single most dangerous failure mode in this design (see §5.3). `llm.py` token-counts each prompt, sets `num_ctx` accordingly, and hard-fails with a loud error if the prompt would exceed the model's practical window. A loud error always beats a silent truncation.
- All prompts are versioned files in `voice_brain/prompts/*.md` with `{{placeholders}}`, version stamped into outputs (`generated_by.prompt_version`) — matching the spec's traceability requirement.

### 5.3 Vault operations (`vault.py`)

- `ensure_folders()` on startup — creates managed folders + `.voice-brain-generated` marker.
- All writes atomic; all reads go through a **vault index** (in-memory, rebuilt on start + `inotify` updates via `watchdog`, optional) with: path, mtime, frontmatter, word count, wikilinks, tags, open TODOs. This makes queries ("what are my open TODOs?", "find notes about X") fast without re-reading the vault each time.
- `.voice-brain-ignore` honored — private notes excluded from index, queries, stats, and creative-output scans.
- **Context strategy (corrected):** device_specs' "1M tokens ≈ 2 GB RAM" claim doesn't survive contact with reality — KV-cache at 1M context is tens of GB, and Ollama's default `num_ctx` (~4096–8192) would **silently truncate** a full-vault prompt, producing plausible-but-wrong answers. So the default query mode is: vault-index prefilter (simple TF ranking, no vector DB needed) → top-K notes → deep lane with `num_ctx` computed as `K × note_tokens + headroom` (typically 16K–32K). Full-vault concatenation survives only as an opt-in config mode (`full_vault_context: always`) that token-counts the vault, sets `num_ctx` to match, and hard-fails if the required KV-cache RAM isn't feasible — never truncates silently.

---

## 6. Note Types (deliverables of each router)

### 6.1 Dream Journal — `dream_journal.py`
- Trigger → prompt `prompts/dream_split.md` (quick lane) returns `{"dreams":[{title, summary, narration_clean, themes, emotional_tone, vividness, lucidity}]}`.
- One file per dream: `Dream Journal/YYYY-MM-DD_{Title_Snake}.md` with full frontmatter from spec (dream_id, vividness, themes, created_by, model, prompt_version).
- Cross-links: after writing, a `## Connections` section gets `[[wikilinks]]` to same-day dreams and (via vault index) recurring theme matches (`themes` overlap with past dreams → "recurring theme: flying, last seen 2025-01-05").
- Notification: `💜 2 dreams saved → Dream Journal/…`.

### 6.2 Daily Journal — `daily_journal.py`
- Trigger → strip prefix, append timestamped entry to `Journal/YYYY-MM-DD.md` (`## HH:MM` header + `---` separator; frontmatter `entry_count` updated). Create file from `templates/daily-journal.md` on first entry of day.
- **Implicit stat capture** (spec): quick-lane LLM pass extracts lightweight tags (`energy:8`, `food:eggs`, `exercise:deadlifts`, `mood:8/10`, `sleep_fragments:2`) appended as invisible HTML comments `<!--vb: mood=8, exercise=strength-->` — never ruining your reading view, fully usable by the stats generator.

### 6.3 Stats Generator — `stats_generator.py` + `stats_schema.py`
- Collects: today's dreams, today's journal (+ implicit tags), creative-output assessment (§6.4), last 7 `Stats/*.json` for trend context.
- Single deep-lane call with `prompts/stats_v1.md` → pydantic `StatsDocument` validation (schema v1.0.0 from the spec, verbatim categories: sleep, mood, energy, physical, nutrition, cognitive, creative_output, social, environment, habits, time_use, derived, insights).
- **Principle: the LLM narrates, code calculates.** Correlations, trend deltas, streaks, anomaly detection and the C/C ratio are computed **deterministically in Python** (`insights.py`) from the last N `Stats/*.json` files and the vault index — Pearson r over rolling windows, z-score anomalies, simple streak counters. The numbers are handed to Gemma *pre-computed*; Gemma's job is interpretation, narrative and recommendations — never arithmetic. This eliminates the #1 failure mode of LLM-driven quantified-self tools: confidently invented correlations (see §13).
- Writes `Stats/YYYY-MM-DD.json`; optional companion `Stats/YYYY-MM-DD.md` human summary (config flag).
- CLI-first: `voice-brain --generate-stats [--date today|yesterday|YYYY-MM-DD]` — same code path for voice trigger, manual run, and nightly timer.
- Nightly **systemd user timer** at 23:59 (config time), plus a catch-up on daemon start if yesterday's stats are missing.

### 6.4 Creative Output Tracking — `creative_output.py`
- At stats time: scan vault for `.md` created/modified today, excluding managed folders + ignored files, `min_note_length_words: 10`.
- Quick-lane batched assessment (multiple notes per call, JSON array out) → dimensions from spec (novelty, depth, connectivity, clarity, actionability, domain, format). Connectivity computed **deterministically** (wikilink density from index) and blended with the LLM's score — LLMs are bad at counting links.
- Feeds `creative_output` block in stats; powers the C/C (consume/create) ratio in `derived`.

### 6.5 General Commands — `notes.py`, `query.py`, `organize.py`
- **create_note**: quick-lane title-gen → write to `Voice Brain Inbox/` (or `--folder` override from natural language, e.g. "create a project note…" → `Projects/`). Frontmatter: `created_by: voice-brain`, tags from LLM.
- **query**: vault index prefilter → top-K notes in context (deep lane) → synthesized answer with `[[citations]]` to source notes, sent as a big notification (and, later, TTS).
- **organize**: **dry-run by default** — produces a diff-plan ("move X → Projects/, add tags #rust") shown in a notification + saved as a note; apply with `voice-brain apply-plan <file>`. Destructive ops never run unconfirmed.
- **brief me**: reads yesterday's stats + today's open TODOs (index scan) → 3–4 sentence morning briefing via notification (TTS in M6).

---

## 7. Visual Interface (minimal, as requested)

**Revised (v2): the visual box** — same Omarchy-overlay aesthetic (dark translucent, rounded, ~92×92 px, corner-anchored), drawing every state live in cairo instead of text labels:

- **armed** → pulsing mic dot
- **recording** → **live waveform bars** driven by real RMS levels from the capture loop
- **transcribing / processing** → **spinning wheel** (covers whisper + gemma load/think time)
- **result** → **checkmark**, color-coded by route (green ✅ notes/journal, purple 💜 dreams, blue 📊 stats) — auto-hides after 2.2 s
- **error** → red ✗

The phone gets the **identical box** (`VisualBoxView`): pulsing dot → waveform → spinner while the laptop thinks → check/✗. Same states, same colors, same size philosophy.

The overlay pill — `ui.py`, GTK4 + gtk4-layer-shell, ~150 lines:

- Anchored top-right (configurable edge), 380×64 px, layer `OVERLAY`, exclusive-zone none, skip-taskbar, ~92% opacity, rounded, blurred background via CSS.
- States rendered as icon + label + (when recording) a 32-bar live RMS level meter:
  - `🎙️ Listening…` (armed, gray pulse) → red while actively detecting speech
  - `✍️ Transcribing…` (amber)
  - `🧠 Thinking…` (purple, spinner)
  - `💜 Dream saved · ✅ Logged · 📊 Stats: 74/100 · 📝 Note created` (green flash, 4 s)
  - `❌ <error>` (red flash)
- Auto-hides when idle. Spawned by the daemon (same process), so no window rules needed — but a Hyprland window rule is added anyway for safety (`float, pin, opacity`).
- **Everything also works headless**: if GTK fails or `$WAYLAND_DISPLAY` is missing, daemon degrades to notify-send-only (config `ui.mode: overlay|notify|none`).

Optional later (M6+): tiny `voice-brain dashboard` command opening a simple local web page (single HTML + Chart.js served on localhost:8477) plotting `Stats/*.json` readiness/creativity radar over time — no server framework, one stdlib `http.server` handler.

---

## 8. Configuration (`~/.config/voice-brain/config.yaml`)

```yaml
vault:
  path: "~/Documents/Obsidian/Omarchy-Yev"
  managed_folders: { dream: "Dream Journal", journal: "Journal", stats: "Stats", inbox: "Voice Brain Inbox" }
  ignore_file: ".voice-brain-ignore"
  full_vault_context: "auto"        # auto|always|never (auto: <120K tokens)

audio:
  source: "default"                  # pactl source name or "default"
  sample_rate: 16000
  arm_timeout_s: 15
  vad_start_rms: 0.02
  vad_start_min_speech_ms: 120
  silence_stop_ms: 1200
  max_recording_s: 90
  spool_retention_days: 7

stt:
  engine: "whisper-cpp"
  model: "base.en"                   # base.en → small.en upgrade path
  language: "en"                     # en | pt | auto (auto is slower)
  beam_size: 5

llm:
  base_url: "http://localhost:11434"
  model_quick: "gemma3:4b"
  model_deep: "gemma4:latest"
  keep_alive: "30m"
  temperature_quick: 0.4
  temperature_deep: 0.3

triggers:  # enable/disable phrase families
  dream: true
  journal: true
  stats: true
  brief: true
  general: true

stats:
  auto_generate: true
  generate_at: "23:59"
  markdown_summary: true
  history_days: 7

creative_output:
  enabled: true
  assess_quality: true

ui:
  mode: "overlay"                    # overlay | notify | none
  position: "top-right"

paths:
  socket: "xdg_runtime/voice-brain.sock"   # resolved at runtime
  models_dir: "~/.local/share/voice-brain/models"
  spool_dir: "~/.local/state/voice-brain/spool"
  logs: "~/.local/state/voice-brain/log"
```

Plus `voice-brain config` interactive doctor: checks Ollama reachable, models present, whisper-cli found, mic source exists, vault writable — prints a ✅/❌ report. This is the first-run experience.

---

## 9. Project Layout

```
voice-brain/
├── pyproject.toml                 # uv project; deps: pyyaml, pydantic, requests (that's ~it)
├── install.sh                     # pacman whisper-cpp, ollama pulls, systemd units, hyprland bind
├── README.md
├── config/default.yaml            # shipped defaults
├── voice_brain/
│   ├── __init__.py
│   ├── main.py                    # CLI: toggle | say | doctor | generate-stats | replay | daemon
│   ├── daemon.py                  # socket server, state machine, orchestrates pipeline
│   ├── client.py                  # thin CLI client (toggle/arm/stop) → unix socket
│   ├── audio.py                   # pw-record/parec capture, RMS VAD gates, ffmpeg downmix
│   ├── stt.py                     # whisper-cli subprocess wrapper, model management
│   ├── llm.py                     # Ollama client, quick/deep lanes, JSON repair loop
│   ├── intent.py                  # trigger regex + LLM intent fallback
│   ├── vault.py                   # index, atomic writes, frontmatter, ignore, wikilink utils
│   ├── dream_journal.py
│   ├── daily_journal.py
│   ├── stats_generator.py
│   ├── stats_schema.py             # pydantic StatsDocument v1.0.0
│   ├── insights.py                 # deterministic correlation/streak/anomaly engine (no LLM math)
│   ├── creative_output.py
│   ├── edits.py                    # undo stack + "fix that"/"scratch that" voice corrections
│   ├── glossary.py                 # vault-derived vocabulary → whisper initial-prompt biasing
│   ├── notes.py                    # create-note, capture fallback
│   ├── query.py                    # vault Q&A
│   ├── organize.py                 # dry-run plans, apply-plan
│   ├── archive.py                  # searchable transcript log of every utterance ("what did I say about…")
│   ├── templates.py                # jinja-less simple {{}} renderer for note templates
│   ├── ui.py                       # GTK4 layer-shell pill (+ notify-send fallback)
│   ├── notify.py                   # notify-send wrapper w/ result formatting
│   ├── config.py                   # load/merge/validate config, path resolution
│   └── prompts/
│       ├── dream_split.md
│       ├── intent_classify.md
│       ├── stats_v1.md
│       ├── creative_assess.md
│       ├── note_draft.md
│       ├── query_answer.md
│       └── brief_me.md
├── templates/                      # note templates (dream, daily journal, project spec…)
├── systemd/
│   ├── voice-brain.service         # user service (daemon, WantedBy graphical-session.target)
│   └── voice-brain-stats.timer/.service
├── tests/
│   ├── fixtures/                   # sample WAVs, sample vault tree, sample LLM responses
│   ├── test_intent.py
│   ├── test_stats_schema.py
│   ├── test_vault.py
│   └── test_e2e_mock.py            # full pipeline with mocked audio+Ollama
└── docs/
    └── SCHEMA.md                   # stats JSON schema documentation
```

**Deliberately light dependency list** (py3.14-proof): `pyyaml`, `pydantic`, `requests`. Everything else is subprocess calls to system binaries or stdlib. No torch, no numpy required (RMS computed with `audioop`/`struct` on raw frames — stdlib).

---

## 10. Omarchy / System Integration

### Keybinding (`~/.config/hypr/`)
```ini
bind = SUPER ALT, V, exec, voice-brain toggle
```
*(Single press toggles arm/stop — matching the hands-free model; a second press mid-recording force-finalizes.)*

### Autostart — systemd user service
```ini
# voice-brain.service
[Unit]
Description=Voice Brain daemon
PartOf=graphical-session.target

[Service]
ExecStart=%h/.local/bin/voice-brain daemon
Restart=on-failure

[Install]
WantedBy=graphical-session.target
```

### Nightly stats — `voice-brain-stats.timer` (OnCalendar=*-*-* 23:59, Persistent=true)
`Persistent=true` covers the "laptop asleep at midnight" case — runs catch-up on next boot, exactly the behavior the spec wanted cron to do but cronie is off.

### Notifications
`notify-send -u normal -t 6000 -a "Voice Brain" "💜 2 dreams saved" "Dream Journal/2025-01-15_…"` — a libnotify **action** (`Retry`, `Delete`) is attached to result notifications where meaningful (GNOME/Omarchy notification daemon supports actions), giving one-click correction of misroutes.

---

## 11. Implementation Roadmap (milestones w/ acceptance criteria)

> **⚠️ Architecture update:** M0–M5 of this roadmap were built in Python and are validated by tests, but the architecture has since pivoted — see **§17**. The Obsidian plugin (TypeScript) becomes the product core (brain + all UI); the Python daemon shrinks to a ~300-line *capture companion* (global hotkey → VAD → whisper → POST transcript). The Python routers/index are retired in favor of Obsidian APIs. M0–M2's audio/STT work survives unchanged inside the companion.

### M0 — Bootstrap & Doctor (½ day)
- [ ] `uv` project scaffold, `pyproject.toml`, config loader, logging
- [ ] `voice-brain doctor`: Ollama reachability + model presence, whisper-cli presence, mic source, vault writability
- [ ] Pull gemma3:4b + gemma4:latest; download ggml whisper base.en
- [ ] **Accept:** `voice-brain doctor` prints all ✅ on your machine.

### M1 — Voice loop: arm → VAD start/stop → transcribe (1 day)
- [ ] Daemon + unix socket + `toggle` client
- [ ] `audio.py`: pw-record capture, RMS start/stop gates, ffmpeg downmix, spool
- [ ] `stt.py`: whisper-cli invocation, model mgmt
- [ ] Notify-send echo of transcript (no LLM yet)
- [ ] **Accept:** press SUPER+ALT+V, speak a sentence, pause — transcript appears in notification ~1–2 s after silence. No words clipped at start/end.

### M2 — Vault layer + Journal + Dream (1 day)
- [ ] `vault.py` index + atomic writes + folder bootstrap
- [ ] Journal router: append w/ timestamps, implicit stat tags
- [ ] Dream router: LLM split → note files w/ frontmatter, quick-lane
- [ ] **Accept:** saying "log this…" appends to today's note; "I had a dream about X and also Y" creates 2 files with titles/frontmatter; both visible in Obsidian instantly.

### M3 — Overlay pill UI (½ day)
- [ ] GTK4 layer-shell pill with all states + level meter, notify fallback
- [ ] **Accept:** pill appears on arm, pulses red while speaking, shows 🧠 while LLM runs, flashes result. Auto-hides.

### M4 — Stats engine (1–1½ days)
- [ ] `stats_schema.py` (pydantic, schema v1.0.0), prompt, JSON repair loop
- [ ] Creative output scan + assessment, connectivity blend
- [ ] CLI `--generate-stats`, markdown companion
- [ ] systemd timer + catch-up
- [ ] **Accept:** a day with 2 dreams + 4 journal entries + 3 created notes yields a valid JSON passing schema validation, and the nightly timer produces it without a voice trigger.

### M5 — General commands (query, create note, organize dry-run, brief me) (1 day)
- [ ] Intent classifier fallback, capture-everything inbox safety net
- [ ] Query with index prefilter + cited answers
- [ ] Organize plan files + `apply-plan`
- [ ] **Accept:** "what do I know about X" answers with wikilink citations; "create a note on Y" lands in Voice Brain Inbox; nothing spoken is ever dropped.

### M6 — Voice-correctness & safety polish (1 day)
- [ ] **"Scratch that" / "fix that"** undo + amend (§16.A1) + `SUPER+ALT+C` cancel key
- [ ] **Low-confidence capture recovery** (§16.A2): whisper avg-logprob gate → "didn't catch that" pill state + replay/retry actions
- [ ] **Glossary biasing** (§16.A3): vault-derived `--initial-prompt` for whisper — big accuracy win on names/projects/technical terms
- [ ] **Continuous dictation mode** (§16.A4): multi-utterance sessions, one armed session → several auto-segmented captures
- [ ] Git snapshot safety net (§16.A6) — auto-commit before any vault mutation if vault has a `.git`
- [ ] Mute-source respect + battery guard for nightly jobs (§16.A8)
- [ ] Hyprland window rule, install.sh, README, `.voice-brain-ignore` docs
- [ ] **Accept:** "scratch that" reverts the last write instantly; saying a project name that previously garbled now transcribes correctly; a `git log` shows a pre-mutation commit.

### M7 — Depth & delight (ongoing / post-v1 runway)
- [ ] `insights.py` deterministic engine wired fully into stats + "what patterns do you see?" voice query
- [ ] Nightly **inbox triage** (§16.B2) — raw captures processed into organized notes via dry-run plans
- [ ] **Weekly Review generator** (§16.B4): "write my weekly review" → `Weekly Reviews/YYYY-Www.md`
- [ ] **Transcript archive queries** (§16.B3): "what did I say last week about X?"
- [ ] TTS replies via Piper — "brief me" spoken aloud
- [ ] Wake word ("hey brain") — *after* VAD loop is battle-tested
- [ ] Local dashboard page for `Stats/*.json` trends (radar over time, creative velocity, streaks)
- [ ] Voice quizzes / spaced repetition (§16.B5)
- [ ] Dream theme clustering (§16.B6) + dream-pattern voice queries
- [ ] Whisper small.en upgrade; PT language config

---

## 12. Testing & Quality Strategy

- **Fixtures, not mocks-of-mocks**: sample 16 kHz WAVs (speech, silence, bilingual), a fake vault tree in `tmp_path`, recorded JSON responses from real Ollama runs.
- **LLM seam**: all LLM calls go through `llm.py`'s `call(prompt, lane)` — tests inject canned responses; one `@pytest.mark.llm_live` marked suite runs against real Ollama and is skipped in CI.
- **Vault safety**: `vault.py` has a `dry_run` mode; every destructive op (move, merge, delete) requires an explicit plan file applied by a separate command — impossible to trigger from voice alone.
- **E2E smoke script**: `voice-brain replay tests/fixtures/dream_sample.wav --route dream` — verifies whole pipeline without a mic.
- **Log**: structured JSONL log in `~/.local/state/voice-brain/log/` (state transitions, latencies per stage) — doubles as the performance dataset for tuning VAD thresholds.

## 13. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Whisper drops first word (common when VAD start is slow) | Keep a 0.5 s **pre-roll ring buffer** always capturing while armed; prepend on start. Cheap and fixes the #1 UX complaint of voice capture. |
| False VAD triggers (fan noise, music) | RMS gate + silero confirmation + config thresholds; `voice-brain doctor --mic` prints a live level meter to calibrate `vad_start_rms`. |
| Gemma JSON non-compliance | Ollama `format:"json"` + pydantic + one repair retry + hard failure falls back to inbox capture (never loses input). |
| Ollama cold-start latency (model unloaded) | `keep_alive:"30m"`; quick lane uses 4b (~2–3 s on this CPU); overlay shows 🧠 so wait is legible. |
| 9b stats generation slow (~30 s) | It's a batch job — acceptable per spec; run async from capture loop (separate thread + own Ollama request). |
| Python 3.14 wheel gaps | Dependency set intentionally tiny (pyyaml/pydantic/requests all ship 3.14 wheels; all audio/STT is native binaries). |
| Bilingual EN/PT transcription | Config `stt.language`; `auto` mode available (slightly slower); LLM output-language mirrors input. |
| Overwriting user-edited notes | Atomic writes + only append to journal; dream/stats files are new files per date; conflict check via mtime before any in-place edit. |
| LLM invents correlations / bad math in stats | `insights.py` computes all correlations, streaks and deltas deterministically; Gemma only narrates pre-computed numbers. LLM can't invent r = 0.72 if r = 0.72 is in the input. |
| STT garbles domain terms / names | whisper.cpp `--initial-prompt` biasing from vault glossary (project names, people, technical terms — see §16.A3). |
| Privacy | Zero network calls except localhost:11434 (verified — no other egress in code); `.voice-brain-ignore`; audio spool retention configurable, purged on schedule; daemon hard-refuses to arm while the mic source is muted in pactl (global privacy kill-switch). |

## 14. Performance Budget (this hardware)

| Stage | Target | Notes |
|---|---|---|
| Arm → speech detected | < 150 ms | RMS gate on live frames |
| Silence → WAV finalized | ~1.2 s | configurable |
| Transcription (base.en) | 0.3–1 s for ≤15 s audio | whisper.cpp int8 CPU |
| Trigger routing | < 10 ms (regex) / ~1.5 s (LLM fallback) | |
| Dream split + write (4b) | 2–4 s | |
| Journal append | < 100 ms | |
| Stats generation (9b) | 20–40 s | async batch, fine |
| **Total round-trip (capture)** | **~3–6 s** | matches spec's dream target |

---

## 15. What makes this a solid product (not a weekend script)

1. **Nothing is ever lost** — every utterance lands somewhere (journal, dream, inbox capture), with spooled audio for retry.
2. **Battle-tested hands-free loop** — pre-roll buffer + two-tier VAD are the difference between "demo" and "daily driver".
3. **Schema-validated, versioned, traceable stats** — every number in `Stats/*.json` links back to source entries; correlations carry `n_day_support`.
4. **Safe-by-construction vault ops** — destructive organization requires explicit plan application; atomic writes; Obsidian never sees a torn file.
5. **Reproducible** — pinned models, versioned prompts, config doctor, structured logs.
6. **Grows with you** — wake word, TTS, dashboard, PT language, and wearable import are all isolated, additive extensions of a small core.

---

## 16. Ideation — Feature Expansion (v2 & beyond)

Ideation on the original spec. Tier A items are **promoted into the core roadmap (M6)** because they fix real weaknesses in a voice-first product; Tier B deepens the product; Tier C is the moonshot drawer.

### Tier A — Core upgrades promoted to M6 (voice UX correctness & safety)

**A1. Voice editing: "scratch that" / "fix that: …"**
Voice-first systems fail without an undo path — STT errors and misroutes are inevitable. The daemon keeps a **last-action ledger** (JSON in state dir): every write records `{files_touched, prior_content_hash, action_metadata}`.
- *"scratch that"* → revert last action (restore prior content from spool/ledger, delete created files that are still unedited — mtime check). Confirm with a 🔄 notification.
- *"fix that: tag it as work"* → quick-lane LLM maps the amendment onto the last artifact (retag, retitle, refile) → applied as a tracked amend, not a blind rewrite.
- `SUPER+ALT+C` (config) cancels any in-flight processing — an escape hatch for the 30 s stats job you triggered by accident.

**A2. Low-confidence capture recovery**
whisper-cli reports per-segment `avg_logprob`. Below a threshold (~-0.8), don't route: pill shows ❓ **"Didn't catch that — say again?"** with notification actions `[Replay]` (plays the spool WAV), `[Retry]` (re-arms), `[Keep]` (saves transcript to Inbox anyway). Every "say again" resolution is logged — and those pairs (bad audio → your correction) are the raw material for a future fine-tune of whisper on your voice (Tier C).

**A3. Glossary biasing — the cheapest big STT win**
whisper.cpp accepts `--initial-prompt`, which biases decoding toward included vocabulary. `glossary.py` harvests the vault index (file titles, `#tags`, `[[links]]`, frontmatter names, project folders — plus a hand-curated `glossary.txt`) and compiles a ~200-token initial prompt like: *"Omarchy, PipeWire, Diconium, Gemma, Whisper, Sous-vide, Sophia, Consultoria …"*. Refreshed nightly at stats time. Names and project words are exactly what generic STT garbles — and exactly what your vault already knows. Works per-language (EN/PT glossaries kept separately).

**A4. Continuous dictation mode**
Arm once, narrate freely — VAD segments utterances and each segment is captured, transcribed and routed *without* re-arming. Triggered by *"start dictation"* or holding the arm key twice. Use cases: narrate a long multi-dream morning (each "I had a dream…" segment becomes its own file), or dictate a full note body while pacing around the room. Ends on *"end dictation"*, keybind, or 10 s silence.

**A5. Clipboard capture**
*"note from clipboard"* → `wl-paste` (Wayland-native, on Hyprland) → content becomes an Inbox note with LLM title/tags. Bridges typed and spoken capture.

**A6. Git snapshot safety net**
If the vault contains a `.git`, `vault.py` snapshots (`git add -A && git commit -m "voice-brain pre-mutation snapshot"`) before any daemon-initiated structural change (organize/apply-plan/move/merge). Appends and new-file creations don't need it. You get a free, browsable audit trail of everything Voice Brain ever did — and time-travel undo for the whole product, not just the last action.

**A7. Bar module (optional)**
Daemon writes a tiny JSON status file (`{state, streaks}`) that an Omarchy bar custom module can render: gray 🎙 idle · red ● recording · 🧠 thinking · 🔥 12-day dream streak. The pill remains primary; the bar widget is a 10-line afterthought, not a dependency.

**A8. Politeness guards**
- **Mute respect**: if the mic source is muted in pactl, the daemon refuses to arm and tells you — the OS mute is the privacy kill-switch and Voice Brain must honor it.
- **Battery guard**: on battery < 30%, nightly stats drops to the 4b lane or defers to next AC session (systemd unit condition + in-daemon check). A QS tool that burns your battery at 23:59 gets uninstalled by day 3.

### Tier B — Product depth (M7+)

**B1. Proactive nudges — closing the insight→action loop**
The stats engine already produces prioritized recommendations. Add an opt-in **nudge scheduler**: tomorrow at the relevant time, the top recommendation fires as a notification: *15:00 — "Afternoon dip day 3 in a row. 15-min walk now?"* Suggested times come from the *evidence* in the stats (the hour the dip occurred). This is the difference between a diary that judges you and a coach that helps you.

**B2. Nightly inbox triage — the capture/processing split**
Inbox captures are raw thought; at 23:30 (before stats), an optional triage pass drafts an **organize plan** from the day's Inbox: which captures become notes, which are answered by existing notes (→ merge as wikilink + TODO), which are junk. You review the plan note in the morning and `voice-brain apply-plan` it. Voice capture only works if processing is effortless.

**B3. Transcript archive — "what did I say last week about X?"**
Every utterance (timestamp, transcript, route, confidence, files touched) is appended to a local JSONL archive. A voice query searches it (TF over transcripts) and synthesizes an answer *from your spoken history* — including things you said but never filed. Your voice becomes a first-class, searchable knowledge source. Retention configurable; encrypted dir optional (`age`-style at-rest, documented recipe).

**B4. Weekly Review generator**
*"write my weekly review"* → deterministic aggregates from 7 `Stats/*.json` (readiness trend, creative velocity, C/C ratio, dream themes, top correlations with real confidence intervals) + deep-lane narrative → `Weekly Reviews/YYYY-Www.md` with an honest "what the data does and doesn't support" section (fed by `insights.py` significance checks — avoids the classic LLM-review sin of finding meaning in noise). Monthly rollup rolls up the rollups.

**B5. Voice quizzes / spaced repetition**
*"quiz me on X"* → notes on X generate Q&A pairs → question shown/spoken → your spoken answer transcribed → quick-lane LLM grades it against the source → **SM-2 scheduling** stored in note frontmatter (`vb_srs: {ease, interval, due}`). Deterministic scheduling, LLM-only grading. All local; no Anki dependency (but Anki export is trivial).

**B6. Dream theme clustering (no embeddings needed)**
TF-IDF over dream-note text + `themes` frontmatter, cosine similarity clustering, recurring-location/character/theme extraction across weeks. Powers: *"Do I dream about flying more when stressed?"* — answered by joining cluster membership with next-day mood scores, computed in `insights.py`. After ~30 dreams this gets genuinely interesting; after 90 it's a personal dream atlas.

**B7. Streaks & gentle gamification**
Journaling streak, dream-recall streak, capture→processing ratio — displayed in pill/bar/"brief me". No badges, no points — just "🔥 12-day capture streak" honesty. Motivation research is clear: visible chains work; shame doesn't.

### Tier C — Moonshot drawer

- **C1. Spoken conversation mode**: wake word + piper TTS + barge-in (VAD interrupt while TTS speaks) — the full heresy: a local assistant that actually talks back. Only after M1–M6 VAD loop is boringly reliable.
- **C2. Fine-tune Whisper on *your* corrections**: A2's retry pairs (garbled audio → corrected transcript) accumulate into a LoRA fine-tune set for whisper-small. Your voice, your vocabulary, your accent — the ultimate personalization, fully local (fine-tune runs overnight on CPU).
- **C3. Mobile companion**: record dreams on waking via phone, drop WAV into a Syncthing folder, Voice Brain ingests and runs the same pipeline on sync. No cloud, no app store.
- **C4. Wearable import**: merge Oura/Whoop/Apple Health CSV exports into Stats JSON — with `source: wearable` vs `source: journal` attribution and the existing `_estimate` flags doing exactly the job they were designed for.
- **C5. Family/team mode**: two vaults, per-speaker STT biasing and journals — "whose dream was that?" speaker classification.
- **C6. Plugin ecosystem**: `voice-brain plugin <dir>` loads extra routers (Python entry points) — community writes new trigger families (recipes, workouts, expenses) without touching the core.

### Config additions introduced by this section

```yaml
editing:
  undo_depth: 10
  cancel_keybind_hint: "SUPER ALT C"

capture:
  dictation_mode: true
  low_confidence_logprob: -0.8

stt:
  glossary_biasing: true
  glossary_file: "~/.config/voice-brain/glossary.txt"   # curated + auto-harvested

safety:
  git_snapshots: "if-present"     # if-present | always | never
  respect_source_mute: true
  battery_guard_percent: 30

insights:
  min_days_for_correlation: 5
  min_n_for_streak: 2

nudges:
  enabled: false                  # opt-in — notifications must be earned, not assumed
  max_per_day: 2

triage:
  enabled: false
  run_at: "23:30"

archive:
  transcripts: true
  retention_days: 365

srs:
  enabled: false
```

---

## 17. Architecture Pivot: Obsidian Plugin Core + Slim Capture Daemon

**Decision (supersedes §2 pipeline ownership):** the product core becomes an **Obsidian plugin (TypeScript)**; the Python daemon remains only as an optional **capture companion** for global-hotkey voice activation. One brain, one source of truth — in the plugin.

### Why

| Current (Python-only) weakness | Plugin fixes it with |
|---|---|
| notify-send walls of text for answers | query modal with clickable `[[wikilinks]]` |
| hand-rolled vault index (mtime cache, TF search) | Obsidian `metadataCache` — links/tags/TODOs for free |
| GTK layer-shell pill | native status bar item |
| dashboard = future local web page | dashboard view rendered inside Obsidian |
| YAML + doctor CLI config | settings tab GUI |
| Omarchy-only | all desktops, Obsidian community store → real Hacktoberfest-scale repo |

All required tech is proven in existing plugins: Node `child_process` spawn of `whisper-cli`/`ffmpeg` (Pandoc, Shellcommands), localhost HTTP server (Local REST API), `getUserMedia`+`MediaRecorder` capture (Audio Recorder).

### The one hard limitation

A plugin only receives keys while **Obsidian is focused** — no global `SUPER+ALT+V`. Since hands-free capture from anywhere (and half-asleep dream capture) is the core UX, the daemon stays as an optional companion. **The plugin is fully standalone**: in-app hotkey capture (mic via getUserMedia + JS VAD) covers everything when Obsidian is focused; the daemon adds global capture + whisper-cli reuse.

### New architecture

```
┌───────────────────────────┐        ┌─────────────────────────────────────────┐
│ voice-braind (Python, slim│        │ voice-brain — Obsidian plugin (TS)      │
│ capture companion)        │  POST  │                                         │
│ SUPER+ALT+V → arm → VAD   │ trans- │ • status bar mic state + streak         │
│ → whisper-cli → transcript├────────▶│ • trigger routing (dream/journal/stats…)│
│ + confidence              │ 127.0.0 │ • Ollama fetch (gemma quick/deep lanes) │
│ fallback: spool jsonl if │ :47799  │ • note writes via Obsidian vault APIs    │
│ plugin offline            │         │ • query modal, stats dashboard view     │
│                           │         │ • settings tab, undo, brief-me          │
│                           │         │ • standalone capture (in-app hotkey +   │
│                           │         │   getUserMedia + WebAudio VAD)          │
└───────────────────────────┘        └─────────────────────────────────────────┘
```

Protocol: `{transcript, ts, confidence, source}` + shared token; plugin ingests daemon spool `jsonl` on startup if it was offline — **never lose input** stays a core invariant.

**Consequence (the "vault connection via extension" principle):** the Python companion is **vault-agnostic** — it never reads or writes a note file again. Every vault operation (note creation, journal appends, frontmatter, link resolution, indexing, queries) happens inside the plugin through the official Obsidian API (`vault.create/process/modify`, `metadataCache`). Direct-FS access from the daemon was the old approach — correct (Obsidian live-reloads external atomic writes, same as obsidian-git), but the extension API is strictly better: instant index, resolved links, modals with clickable citations, and it follows the user's Obsidian settings.

**Extension-only limitation, restated:** the plugin runs only while Obsidian is open — the spool ingest and launch-time catch-up ("generate missing stats days") cover the gap; the 23:59 systemd timer stays as belt-and-suspenders while Omarchy is the target platform.

### Plugin module map

```
voice-brain-plugin/
├── manifest.json, styles.css, main.ts
├── src/
│   ├── settings.ts        # settings tab + config persistence (folders, models, thresholds)
│   ├── statusbar.ts       # mic state icon + capture streak
│   ├── capture.ts         # standalone: getUserMedia + MediaRecorder + AnalyserNode VAD
│   ├── stt.ts             # spawn whisper-cli (+ffmpeg wav convert); initial-prompt glossary biasing
│   ├── daemon.ts          # localhost HTTP server; spool ingest; daemon health ping
│   ├── llm.ts             # Ollama fetch; explicit num_ctx; JSON-mode + repair retry
│   ├── intent.ts          # phrase triggers (ported from Python regex)
│   ├── routes/
│   │   ├── dream.ts journal.ts stats.ts query.ts notes.ts vaultops.ts brief.ts
│   ├── insights.ts        # pearson/streaks/zscore (ported) — LLM narrates, code calculates
│   ├── schemata/stats.ts   # stats v1.0.0 validation (ported)
│   ├── ui/
│   │   ├── query-modal.ts answer-view.ts (clickable wikilinks)
│   │   ├── dashboard.ts radar + readiness/creativity trends (SVG, no deps)
│   │   └── settings-tab.ts
│   └── i18n/ en.ts pt.ts
└── tests/ (vitest)        # router tests ported from the Python suite
```

### Reuse / port / retire

- **Keep (Python companion):** `audio.py`, `stt.py`, `client.py` + slimmed `daemon.py` (relay only) ~300 lines
- **Port to TS:** intent regexes, prompts (strings), stats schema validation, insights math, note templates
- **Retire:** Python routers, `vault.py` index, GTK `ui.py`, unix-socket protocol (HTTP), `notes.py`/`query.py`/`vault_ops.py`
- **Unchanged principles:** num_ctx hard-fail discipline, LLM-narrates/code-calculates, capture-everything safety net, dry-run organize plans, glossary STT biasing, transcript archive

### Revised milestones

- **P0 — plugin scaffold** (obsidian sample-plugin TS base, manifest, status bar, settings tab stub) — ½ day
- **P1 — standalone capture loop** (getUserMedia + VAD + whisper-cli spawn + status bar states) — 1 day
- **P2 — brain port** (intent routes, Ollama client, dream/journal/stats/note writers via vault API, undo) — 1–1½ days
- **P3 — query modal + dashboard view** — 1 day
- **P4 — daemon companion protocol** (HTTP server + spool ingest; slim Python daemon relay) — ½ day
- **P5 — polish** (i18n en/pt, README, community-plugin submission checklist) — ½ day
- **P6 — mobile gesture capture** (see §18) — 1 day

### Community-plugin submission notes

- Requirements: `manifest.json` (min App version), README screenshots, GPLv3/MIT license — MIT chosen
- Plugin id: `voice-brain` (check registry collision at submission)
- Keep zero required network beyond `localhost` — a selling point; state it in the README

---

## 18. Mobile Capture with a Gesture (P6)

**Requirement:** capture dreams/journal/notes from the phone, triggered by a physical gesture, fully local-first. Promotes §16.C3 from moonshot drawer to first-class feature.

### Gesture per platform

| Platform | Gesture | Implementation |
|---|---|---|
| **Android** | Hold power button / corner swipe (OS assistant gesture); QS tile + lockscreen shortcut as alternates | Tiny "Voice Brain Capture" app (~200 lines Kotlin): registered as the **Digital Assistant app** → record with silence auto-stop → POST |
| **iOS** | **Back Tap** (Settings → Accessibility → Touch → Back Tap → run shortcut) | Apple Shortcut, zero app code: Record audio (or on-device Dictate) → POST to daemon |

The Android assistant-registration path is the gold standard UX: the gesture works from the lock screen, half-asleep, no app opening — exactly the dream-capture scenario.

### Transport (local-first, no cloud ever)

```
phone (gesture → record) ──▶ POST https://<tailscale-host>:47799/api/capture
                              (Tailscale p2p mesh or home LAN, bearer token)
                                    │
                                    ▼
                        daemon: ffmpeg decode (m4a/opus/aac → 16k mono wav)
                               → whisper-cli → existing pipeline → vault
                                    │
                        HTTP response = result summary (phone shows local notif)

offline fallback: phone drops file into Syncthing folder VoiceBrain/Capture/
                  → daemon folder-watcher ingests on arrival (dedup by capture id)
```

### Capture server — hosted by whichever component owns the vault in that profile

**Two deployment profiles, one HTTP surface (same port, same protocol):**

- **Relay profile** (Obsidian open locally): the **plugin** hosts the server — it owns the vault via Obsidian APIs. Daemon + phone are clients.
- **Standalone profile** (Obsidian lives elsewhere — e.g. vault synced via CouchDB/Self-hosted LiveSync): the **Python daemon** hosts the identical API (`http_api.py`, port 47799) and runs the full local pipeline, writing the vault folder directly. LiveSync picks up the atomic writes and syncs them through CouchDB to all devices — Obsidian never needs to be open on the capture machine. The daemon also drains its own pending spool through the pipeline on startup in this mode.

The Android app can't tell the difference — same `POST /api/capture`, same `X-VB-Token`.

- Plugin server (node `http`, port 47799): `POST /utterance` `{text, source, ts, confidence}` from the daemon (already transcribed) and `POST /api/capture` raw audio bytes (`X-VB-Filename`, `X-VB-Token` headers) from the Android app
- `GET /health` — daemon and app show friendly errors when the laptop/Obsidian is unreachable
- Bind host configurable: `127.0.0.1` (default, daemon-only) or LAN/tailscale IP for phone access — **token required** when binding beyond localhost
- Fallbacks when the plugin is down: daemon appends to `pending.jsonl` (ingested by the plugin on startup); phone saves to the Syncthing folder (ingested by the plugin's folder watcher)
- Phone captures enter the same ledger/archive pipeline (source: `phone`/`syncthing`) — indistinguishable from desktop captures downstream

### Build order (status)

1. ✅ Plugin capture server + ffmpeg/whisper decode (built — `voice-brain-plugin/src/server.ts`, `src/stt.ts`)
2. ✅ Android capture app: assistant-gesture registration + QS tile + VAD silence auto-stop + WAV upload (scaffolded — `voice-brain-android/`, open in Android Studio to build the APK)
3. ✅ Syncthing folder ingest + daemon pending-spool ingest (built — plugin `server.ts` ingest functions; Python `relay.py`)
4. ⬜ iOS Shortcut (trivial once the server is reachable from the phone — same endpoint as Android)

---

## 19. Build Status (first full pass)

| Component | State | Notes |
|---|---|---|
| `voice-brain/` (Python companion) | ✅ 51/51 tests green | mic capture, VAD, whisper-cli, relay mode (POSTs transcripts to the plugin, pending-spool fallback), legacy standalone pipeline retained as no-Obsidian fallback |
| `voice-brain-plugin/` (Obsidian, TS) | ✅ typechecks + bundles (main.js, esbuild) | the brain: routes (dream/journal/stats/notes/query), Ollama client w/ num_ctx discipline, deterministic insights engine, stats schema validation, undo ledger, status bar, query modal w/ clickable wikilinks, SVG dashboard, settings tab, localhost capture server, offline ingest |
| `voice-brain-android/` (Kotlin) | ✅ scaffolded (build in Android Studio) | assistant-gesture registration (hold power), QS tile, AudioRecord VAD auto-stop, WAV upload, Syncthing offline fallback, no third-party deps |
| Models | ✅ gemma3:4b + gemma4:latest pulled; ggml-base.en downloaded | gemma3:9b no longer in registry — deep lane points at gemma4:latest (7.5B, 131k ctx) |
| Installed & live-verified | ✅ (2026-10-17) | whisper-cpp installed; `install.sh` completed; daemon + stats timer running via systemd; **standalone profile active** (user syncs vault via CouchDB/Self-hosted LiveSync); end-to-end tests passed: real audio → whisper → gemma intent → vault write → undo; phone-protocol audio POST through the standalone API → vault write; spool drain → journal entry |
| v2 additions (2026-10-17, user requests) | ✅ live | Hyprland bind `SUPER+ALT+V` wired into `~/.config/hypr/bindings.lua` (omarchy skill, validated with `hyprctl configerrors`); **deep lane switched to gemma4:12b**; laptop **visual box** (waveform/spinner/check, `ui.py` v2); phone **visual box** (`VisualBoxView.kt`); **LAN discovery — no hardcoded IPs**: daemon answers UDP `VB_DISCOVER` (:47798) with name+port, phone scans via broadcast **and /24 unicast sweep** (this AP drops broadcast); capture API bound `0.0.0.0:47799` + auth token; `PYTHONUNBUFFERED` in the systemd unit |
| Not yet done | ⬜ | Android APK build (open `voice-brain-android/` in Android Studio), plugin install (optional UI), live mic capture test (needs a human voice) |

---

## 20. User-Editable Pattern Routing + Transcript Polishing (v3)

**User requirements (2026-10-17):** (1) every raw transcript goes through Gemma for cleanup/structure, (2) pattern→folder routing like "I have an idea…" → `Projects/`, (3) patterns must be **user-editable, not hardcoded**, and **synchronized between the daemon and the plugin across all devices**.

### The patterns note — one source of truth, synced by LiveSync

`<vault>/Voice Brain Settings/patterns.md` — a plain editable note:

```
I had a dream|dream
I have an idea|note|Projects
log this|journal
scratch that|scratch
```

Line format: `<pattern> | <route> [| <folder>]` · routes: dream/journal/note/capture/query/stats/brief/scratch · first match wins · payload = utterance minus the pattern · patterns are regexes (case-insensitive); broken ones are skipped, never crash routing.

Both consumers parse the same file: the Python daemon (`patterns.py`, mtime-cached reload) and the Obsidian plugin (`patterns.ts`, vault-API read). Editing it on any device changes routing everywhere because **LiveSync syncs the note itself**. Creation is defensive: if the folder layout fights us (e.g. a file named "Settings"), the daemon degrades to built-in triggers instead of crash-looping.

### Transcript polishing

`prompts.polish_note`: raw voice → JSON `{title, content, tags}` — fillers/false starts removed, bullets and structure added, meaning preserved exactly. Raw transcript is appended at the bottom of every polished note (never lose input). Routes:

- `note` patterns ("I have an idea…") → polished note into the **rule's folder** (Projects, or any)
- unknown/general utterances → polished note into Voice Brain Inbox (previously verbatim)
- LLM down → verbatim capture + loud error (safety net unchanged)
- **Journal stays verbatim** — it's a log (spec: "preserved as-is"); dream route keeps its dedicated splitter prompt

Live-verified end-to-end: "I have an idea: a small device that reminds me to water the plants…" → 32s through gemma4:12b → `Projects/2026-10-17_Plant_Care_Assistant_Device.md` with 4 clean bullets, tags, and raw transcript preserved.

### Plugin distribution across devices (LiveSync)

- The **patterns note syncs natively** (it's a vault file) — this is the synced configuration surface.
- The plugin binary lives in `.obsidian/plugins/` — **LiveSync skips hidden dot-folders by default**. Options: enable *Hidden File Sync* in Self-hosted LiveSync's settings (experimental), or copy the 3 files (`manifest.json`, `main.js`, `styles.css`) per desktop. The plugin is desktop-only (`isDesktopOnly` — spawns whisper/ffmpeg), so Obsidian mobile never runs it anyway; phones use the Android capture app + LiveSync'd vault.

---

## 21. Multilingual: EN + PT-PT + RU (v4)

**Layers:**

1. **STT**: whisper model switched `base.en` → **`small`** (multilingual — `.en` models physically cannot transcribe pt/ru), `language: auto` → per-capture detection. The Android app is untouched (audio-only; the laptop transcribes).
2. **Triggers**: the patterns note gained PT-PT and Russian sections (`tive um sonho|dream`, `anota isto|journal`, `мне снился сон|dream`, `запиши это|journal`, `у меня есть идея|note|Projects`…) — LiveSync distributes the file, so all three languages route identically on every device. Python `re` and TS `RegExp` both handle Cyrillic/diacritics; TS word-matching fixed to Unicode property escapes (`\p{L}`) for glossary biasing + search (ASCII `\w` would have dropped Cyrillic terms).
3. **LLM**: every prompt's LANG_RULE hardened after live testing caught gemma translating a Russian journal heading into English ("Productive Day"): now "NEVER translate — Russian in, Russian out". Re-verified: `запиши это: сегодня был хороший день` → `## Хороший день` ✓. Tag *keys* and stats categories stay English (machine-parseable); all human text mirrors the spoken language.

Live-verified: PT (`anota isto: hoje acordei cedo…` → `## Manhã com Café`, 22s) and RU (`запиши это: …` → `## Хороший день`) through gemma4:12b end-to-end. 60/60 tests.

---

## 22. Raw transcripts in the inbox + structured per route (v5)

**The invariant: your words and the model's words live in different places.**

- **`Voice Brain Inbox/{date}_transcript-{HHMMSS}.md`** — the *verbatim whisper transcript*, written **before any LLM runs**, for every capture from every source (`source`/`route`/`confidence` in frontmatter). Not in the undo ledger — it survives LLM crashes, `scratch that`, and undo (never lose input). LiveSync ships it to every device.
- **Route folders** — gemma's structured output only: `Projects/…`, `Journal/YYYY-MM-DD.md`, `Dream Journal/…`, stats, etc. The old `## Raw transcript` block at the bottom of polished notes is gone (no duplication).
- Every path funnels through `daemon._process_text` (now also the phone/HTTP path) which now returns `(state, title, body)` and appends to the JSONL spoken-history archive.
- **Glossary guard**: whisper biasing no longer feeds attachment/machine filenames (`PXL_*.jpg`, `CIA-*.pdf`, `*~2` artifacts) — they were actively hurting transcription.

## 23. Plugin model control (v5)

Settings → Ollama now lists **live dropdowns** of every installed model (via `GET /api/tags`) for deep- and quick-lane, with text fallback when Ollama is unreachable, a **"use one model for everything"** toggle (mirrors deep→quick), and a refresh button.

## 24. The plugin as the control center (v6)

**Fixed: whisper was TRANSLATING foreign speech into English.** Root cause: the vault-glossary `--prompt` (English "Vocabulary: …" tokens) under `language: auto` biases the decoder — whisper's prompt carries language. User's PT capture came out as English ("preço fixo" → "pressfix"), which then missed the PT trigger patterns → fell to `general` → wrong folder. Both reported symptoms, one bug. Fix: glossary biasing only applies when the language is **pinned** (auto = no prompt).

**Voice Brain Settings/settings.md** — the synced settings file (LiveSync carries it; the daemon hot-reloads it before every capture — verified live: `[settings] live-reloaded: stt_language=pt, …`). Keys: `stt_language`, `stt_model`, `quick_model`, `deep_model`, `overlay`, `silence_stop_ms`, `keep_alive`.

**Plugin settings tab reworked into the control center** (nothing is "local-only" anymore except Ollama URL and folders):
- **Models (synced)** — dropdowns fed live from Ollama + one-model toggle
- **Voice & capture (synced)** — language (auto/en/pt/ru), whisper model, laptop overlay, silence auto-stop
- **Speech patterns (synced)** — full table editor (pattern/route/folder, add/remove/reorder) writing the same `patterns.md` the daemon and phone follow
- The plugin itself follows the synced values on load (vault file wins over data.json)

65/65 tests. LiveSync now carries: patterns.md + settings.md + every transcript note — one settings surface for phone + laptop + desktops.

## 25. The plugin on mobile (v7)

- **Plugin binaries sync through CouchDB**: LiveSync *Plugin sync v2* was already enabled but unconfigured; set `pluginSyncExtendedSetting["voice-brain"] = {mode: MODE_AUTOMATIC(1), files: [main.js, manifest.json, styles.css]}` (schema reverse-engineered from the bundled main.js). `data.json` (per-device local settings) deliberately NOT synced. Requires one Obsidian restart to take effect.
- **The plugin is mobile-capable**: `isDesktopOnly` removed. Node builtins (child_process/fs/os/path) in stt.ts are now **lazy `require()`s** so the module graph loads under mobile's JS runtime; mic capture / HTTP server / offline ingest are gated behind `Platform.isDesktopApp`. On mobile the plugin is a settings+reading surface (patterns editor, synced settings, queries, dashboard, undo). STT calls on mobile throw a clear "desktop-only" error instead of crashing.
- What works on phone Obsidian: edit patterns/models/language (writes the synced vault files → laptop daemon picks them up on next capture), browse notes, query the brain if Ollama is reachable (set the LAN/Tailscale URL in the plugin's local settings on the phone).

*Next step (revised): scaffold the Obsidian plugin (P0) and port the brain (P2) — the Python companion work is done and waiting. P6 mobile capture depends only on the daemon HTTP API.*
