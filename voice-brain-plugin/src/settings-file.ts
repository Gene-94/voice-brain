/** Vault-synced settings — Voice Brain Settings/settings.md.
 *
 *  The single source of truth shared by the Obsidian plugin, the Python
 *  daemon (laptop capture) and — through it — the phone. LiveSync carries the
 *  file to every device; the daemon hot-reloads it before each capture.
 *  Format: `key: value` per line (same whitelist as Python settings_sync.py). */

import { App, normalizePath, TFile } from "obsidian";

export const SETTINGS_PATH = "Voice Brain Settings/settings.md";

export const SYNCED_DEFAULTS = `# Voice Brain — settings (synced to all devices)

# Managed from the Obsidian plugin (Settings -> Voice Brain); the daemon
# hot-reloads this file. Phone and PC both follow it. Edit by hand if you like.

stt_language: auto        # auto | en | pt | ru  (per-capture detection)
stt_model: small          # whisper model (.en models are English-only)
quick_model: gemma4:12b   # fast lane: tags, titles, intent
deep_model: gemma4:12b    # reasoning lane: notes, stats, queries
overlay: overlay          # laptop capture UI: overlay | notify | none
silence_stop_ms: 1200     # laptop mic: ms of silence that ends a capture
keep_alive: 30m           # keep models resident in ollama
`;

export type SyncedValues = Record<string, string>;

export async function ensureSettingsFile(app: App): Promise<void> {
  const path = normalizePath(SETTINGS_PATH);
  if (!app.vault.getAbstractFileByPath(path)) {
    const folder = normalizePath(SETTINGS_PATH.split("/").slice(0, -1).join("/"));
    if (!app.vault.getAbstractFileByPath(folder)) {
      await app.vault.createFolder(folder);
    }
    await app.vault.create(path, SYNCED_DEFAULTS);
  }
}

export async function readSyncedSettings(app: App): Promise<SyncedValues> {
  await ensureSettingsFile(app);
  const file = app.vault.getAbstractFileByPath(normalizePath(SETTINGS_PATH)) as TFile;
  const text = await app.vault.read(file);
  const out: SyncedValues = {};
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes(":")) continue;
    const idx = line.indexOf(":");
    const value = line.slice(idx + 1);
    const hash = value.indexOf("#");
    out[line.slice(0, idx).trim()] =
      (hash >= 0 ? value.slice(0, hash) : value).trim();
  }
  return out;
}

export async function writeSyncedSettings(
  app: App, updates: SyncedValues,
): Promise<void> {
  await ensureSettingsFile(app);
  const file = app.vault.getAbstractFileByPath(normalizePath(SETTINGS_PATH)) as TFile;
  const current = await readSyncedSettings(app);
  const merged = { ...current, ...updates };
  // rewrite the file with the canonical header; values sorted for stable diffs
  const lines = Object.entries(merged)
    .filter(([, v]) => v !== "" && v !== undefined)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}: ${v}`);
  const body = [
    "# Voice Brain — settings (synced to all devices)",
    "",
    "# Managed from the Obsidian plugin (Settings → Voice Brain); the daemon",
    "# hot-reloads this file. Phone and PC both follow it. Edit by hand if you like.",
    "",
    ...lines,
    "",
  ].join("\n");
  await app.vault.modify(file, body);
}
