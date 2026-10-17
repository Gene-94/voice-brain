# 🧠 Voice Brain

> **A whisper for your Obsidian vault — powered entirely by your own machine.**
> Speak into your phone. Whisper hears you, Gemma structures your thoughts, and a clean note lands in your vault. No cloud, no API keys, no subscriptions — ever.

**Hackathon submission** · 100% local voice-first knowledge assistant

---

## What it does

Pick up your phone, speak naturally — and watch the thought appear in Obsidian, already structured:

```
 📱 phone (gesture / tile)          💻 your laptop (fully local)                 📓 Obsidian
┌────────────────────┐   audio    ┌──────────────────────────────┐   note    ┌─────────────┐
│  hold power →      │ ─────────▶ │  whisper.cpp (small)         │ ────────▶ │ Projects/   │
│  speak your idea   │            │  auto-detects EN / PT / RU   │           │ Journal/    │
│  tap to send       │            │        ↓                     │           │ Dream Journal│
└────────────────────┘            │  gemma4 via Ollama           │           └─────────────┘
                                  │  routes + structures + tags  │
                                  └──────────────────────────────┘
```

Say this:

> *"I have an idea: a mug that keeps coffee at exactly 55 degrees and shows the temperature on a tiny e-ink display"*

Get this — `Projects/2026-10-17_Smart_Mug_with_E-Ink_Display.md`, with frontmatter, tags, and bullet structure — on every device you own, via [Self-hosted LiveSync](https://github.com/vrtmrz/obsidian-livesync).

## ✅ What's working (this is live, not a mockup)

| Capability | Status |
|---|---|
| 📱 **Android capture app** — power-button gesture or quick-settings tile → speak → tap to send | ✅ shipped |
| 🎙️ **Whisper transcription on the laptop** — `whisper.cpp`, multilingual (`small` model): English, Português (PT), Русский, auto-detected per capture | ✅ live |
| 🧠 **Gemma structures your notes** — local Ollama, one model for everything (gemma4) | ✅ live |
| 🤖 **Zero-config discovery** — the phone scans the LAN, finds the laptop's Ollama-powered daemon, pairs with a 6-digit PIN (LocalSend-style) | ✅ live |
| 🗂️ **Smart routing by trigger patterns** — *"I have an idea"* → Projects, *"log this"* → Journal, *"I had a dream"* → Dream Journal… in EN/PT/RU | ✅ live |
| 🛡️ **Nothing is ever lost** — every raw transcript is preserved in a `Voice Brain Inbox` note *before* the LLM touches it; undo ledger for everything else | ✅ live |
| 📊 **Nightly quantified-self stats** — 23:59 systemd timer builds your day through the local LLM | ✅ live |
| ⌨️ **Laptop capture too** — `SUPER+ALT+V` hotkey, translucent overlay UI | ✅ live |
| 🔧 **Manage everything from Obsidian** — the plugin's settings tab edits speech patterns, models, and language — synced to phone + laptop through the vault itself | ✅ live |
| 🔌 Works offline — airplane-mode LAN, no internet required after install | ✅ live |

## How the pieces fit

```
voice-brain/           Python daemon — the pipeline (STT → intent → LLM → vault)
voice-brain-plugin/    Obsidian plugin — settings hub, queries, dashboard, undo
voice-brain-android/   Android app — your microphone, everywhere you are
```

**The clever bit:** there is no config server and no account system. The *vault itself* is the config bus — `patterns.md` and `settings.md` are ordinary notes that LiveSync replicates to every device, and the daemon hot-reloads them before every capture. Change a trigger phrase on your phone; your laptop obeys on the very next word you speak.

## Quick start

**Laptop** (the brain — Arch/Python):

```bash
git clone https://github.com/Gene-94/voice-brain && cd voice-brain
./install.sh          # whisper-cpp + uv + ollama models + systemd services
voice-brain pair      # shows a 6-digit PIN for the phone
```

**Phone** (the voice): install the APK from `voice-brain-android/`, open it → **Scan** finds your laptop → enter the PIN → **Test**. Then set *Voice Brain Capture* as your Digital Assistant app: from then on, **hold the power button and just talk.**

Everything else — patterns, models, language — lives in Obsidian → Settings → Voice Brain.

## Privacy model

Your voice never leaves your LAN. Audio → transcript → LLM → note, all on hardware you own. The only network traffic is your phone talking to your laptop (token-authenticated, subnet-scoped firewall rule).

## Tech

`whisper.cpp` · `Ollama (gemma4)` · Python · TypeScript (Obsidian API) · Kotlin (Android) · systemd · CouchDB/Self-hosted LiveSync

---

*Built for the hackathon — every feature listed above was tested end-to-end on real hardware: a ThinkPad, a Pixel phone, and one very patient vault.*
