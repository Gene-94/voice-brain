# Voice Brain Capture (Android)

Tiny companion app (~300 lines Kotlin) for [Voice Brain](../voice-brain-plugin).
Trigger with a **gesture**, speak, silence auto-stops — audio goes to the Obsidian
plugin's capture server over your LAN/Tailscale. No cloud, ever.

## Gestures (pick any)
1. **Assistant gesture (best):** Settings → Apps → Default apps → Digital Assistant app →
   *Voice Brain Capture*. Then **hold the power button** (or corner-swipe) anywhere,
   even on the lock screen → speak → done.
2. **Quick Settings tile:** swipe down, tap the 🎙️ *Voice Brain* tile.
3. **Home screen:** launch like any app (MainActivity also has settings).

## Setup
1. In Obsidian → Voice Brain settings: set **Bind host** to `0.0.0.0` (or your
   Tailscale IP) and set an **Auth token**.
2. Install this app, open it once, enter:
   - **Server URL:** `http://<laptop-ip-or-tailscale-hostname>:47799/api/capture`
   - **Token:** the same token as in the plugin
   - Tap *Test connection* → should say `OK`.
3. Optional offline path: set a **Syncthing folder** — recordings are saved there when
   the laptop is unreachable; the plugin ingests them when it syncs.

## Build
Open this folder in Android Studio (or run `gradle wrapper && ./gradlew assembleDebug`).
Requires: AGP 8.x, Kotlin 2.0, minSdk 26. No third-party dependencies.

## How it records
AudioRecord (16 kHz mono PCM) with an RMS voice-activity gate — same state machine as
the desktop daemon: speech detected → record starts; 1.2 s silence → stop; then a real
WAV is POSTed (or saved offline). The plugin does STT + routing + vault writes.
