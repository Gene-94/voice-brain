/** Settings + shared types. Mirrors the Python companion's config semantics. */

export interface VBSettings {
  // vault folders (created if missing)
  dreamFolder: string;
  journalFolder: string;
  statsFolder: string;
  inboxFolder: string;

  // ollama
  ollamaUrl: string;
  modelQuick: string;
  modelDeep: string;
  temperatureQuick: number;
  temperatureDeep: number;
  maxNumCtx: number;
  keepAlive: string;

  // stt
  language: string; // "auto" (recommended) | "en" | "pt" | "ru" — per-capture detection
  whisperModel: string; // multilingual model required for pt/ru (e.g. "small")
  glossaryBiasing: boolean;

  // capture
  captureVadRms: number;
  captureSilenceMs: number;
  captureMaxS: number;

  // server (receives hotkey transcripts from the Python daemon + phone audio)
  serverEnabled: boolean;
  serverPort: number;
  serverBindHost: string; // 127.0.0.1 (local only) or 0.0.0.0 (LAN/Tailscale — set a token!)
  serverToken: string;

  // offline ingest
  pendingFile: string; // Python daemon's unrelayed transcript spool
  captureFolders: string; // comma-separated Syncthing folders with phone recordings

  // stats
  statsHistoryDays: number;
  statsMarkdownSummary: boolean;

  // undo
  undoDepth: number;
}

export const DEFAULT_SETTINGS: VBSettings = {
  dreamFolder: "Dream Journal",
  journalFolder: "Journal",
  statsFolder: "Stats",
  inboxFolder: "Voice Brain Inbox",

  ollamaUrl: "http://localhost:11434",
  modelQuick: "gemma3:4b",
  modelDeep: "gemma4:latest",
  temperatureQuick: 0.4,
  temperatureDeep: 0.3,
  maxNumCtx: 32768,
  keepAlive: "30m",

  language: "auto",
  whisperModel: "small",
  glossaryBiasing: true,

  captureVadRms: 0.02,
  captureSilenceMs: 1200,
  captureMaxS: 90,

  serverEnabled: true,
  serverPort: 47799,
  serverBindHost: "127.0.0.1",
  serverToken: "",

  pendingFile: "~/.local/state/voice-brain/pending.jsonl",
  captureFolders: "",

  statsHistoryDays: 7,
  statsMarkdownSummary: true,

  undoDepth: 10,
};

export interface FileOp {
  path: string; // vault-relative
  op: "create" | "modify";
  prior: string | null; // prior content (null => creation)
  afterSha: string; // sha256 of the content we wrote (undo safety)
}

export interface LedgerAction {
  ts: number;
  description: string;
  ops: FileOp[];
}

export interface LedgerData {
  actions: LedgerAction[];
}

export interface Utterance {
  text: string;
  source: "hotkey" | "phone" | "in-app" | "spool" | "syncthing";
  ts: number;
  confidence?: number | null;
}
