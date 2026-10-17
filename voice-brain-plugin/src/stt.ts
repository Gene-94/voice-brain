/** Desktop STT: spawn whisper-cli (+ ffmpeg decode).
 *  Node builtins are imported LAZILY inside methods so this module (and the
 *  whole plugin) loads on mobile too — calls just fail with a clear error. */

import type { App, TFile } from "obsidian";
import { normalizePath } from "obsidian";
import type { VBSettings } from "./types";

export class STTUnavailable extends Error {}

export interface Transcription {
  text: string;
  avgLogprob: number | null;
}

/** Desktop guard: everything below needs Node (child_process/fs/os/path). */
async function node<T>(what: string): Promise<T> {
  if (!(await import("obsidian")).Platform.isDesktopApp) {
    throw new STTUnavailable(
      `whisper STT is desktop-only (${what}) — use the phone capture app or the laptop hotkey`);
  }
  return (await import(what)) as unknown as T;
}

function which(bin: string): string | null {
  // sync callers: this file is only reached on desktop (see node())
  const pathMod = require("path") as typeof import("path");
  const fsMod = require("fs") as typeof import("fs");
  const paths = (process.env.PATH ?? "/usr/bin:/usr/local/bin").split(pathMod.delimiter);
  for (const p of paths) {
    const candidate = pathMod.join(p, bin);
    try {
      fsMod.accessSync(candidate, fsMod.constants.X_OK);
      return candidate;
    } catch {
      /* keep looking */
    }
  }
  return null;
}

function run(cmd: string, args: string[], timeoutMs = 300_000): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const { spawn } = require("child_process") as typeof import("child_process");
    const proc = spawn(cmd, args);
    let out = "";
    let err = "";
    const timer = setTimeout(() => proc.kill(), timeoutMs);
    proc.stdout.on("data", (d) => (out += d));
    proc.stderr.on("data", (d) => (err += d));
    proc.on("error", (e) => {
      clearTimeout(timer);
      reject(new STTUnavailable(`${cmd} not runnable: ${e.message}`));
    });
    proc.on("close", (code) => {
      clearTimeout(timer);
      resolve({ code: code ?? 1, stdout: out, stderr: err });
    });
  });
}

export class Stt {
  constructor(private s: VBSettings) {}

  modelPath(): string {
    const pathMod = require("path") as typeof import("path");
    const osMod = require("os") as typeof import("os");
    return pathMod.join(osMod.homedir(), ".local", "share", "voice-brain", "models",
                     `ggml-${this.s.whisperModel}.bin`);
  }

  modelPresent(): boolean {
    try {
      const fsMod = require("fs") as typeof import("fs");
      return fsMod.statSync(this.modelPath()).size > 1_000_000;
    } catch {
      return false;
    }
  }

  async available(): Promise<boolean> {
    return which("whisper-cli") !== null && this.modelPresent();
  }

  /** Decode any phone/browser codec (m4a/opus/webm/aac) to 16 kHz mono WAV. */
  async decodeToWav(input: string): Promise<string> {
    if (input.endsWith(".wav")) return input;
    if (!which("ffmpeg")) {
      throw new STTUnavailable("ffmpeg not found — install it to decode phone audio (pacman -S ffmpeg).");
    }
    const out = input.replace(/\.[^.]+$/, "") + ".vb.wav";
    const res = await run("ffmpeg", ["-y", "-i", input, "-ac", "1", "-ar", "16000",
                                     "-sample_fmt", "s16", out], 120_000);
    if (res.code !== 0) throw new STTUnavailable(`ffmpeg decode failed: ${res.stderr.slice(0, 200)}`);
    return out;
  }

  async transcribe(wavPath: string, initialPrompt?: string): Promise<Transcription> {
    const cli = which("whisper-cli");
    if (!cli) throw new STTUnavailable("whisper-cli not found. Install: sudo pacman -S whisper-cpp");
    if (!this.modelPresent()) {
      throw new STTUnavailable(
        `whisper model missing: ${this.modelPath()} (run the Python companion's 'voice-brain doctor --setup')`);
    }
    const outBase = wavPath.replace(/\.wav$/, "");
    const args = [
      "-m", this.modelPath(),
      "-f", wavPath,
      "-bs", "5",
      "-oj", "-of", outBase,
      "-np",
    ];
    if (this.s.language && this.s.language !== "auto") args.push("-l", this.s.language);
    if (initialPrompt) args.push("--prompt", initialPrompt.slice(0, 400));

    const res = await run("whisper-cli", args);
    if (res.code !== 0) throw new STTUnavailable(`whisper-cli failed: ${res.stderr.slice(0, 300)}`);

    const logprobMatch = res.stdout.match(/avg_logprob\s*=\s*(-?\d+\.?\d*)/);
    const avgLogprob = logprobMatch ? parseFloat(logprobMatch[1]) : null;

    let text = "";
    try {
      const fsMod = require("fs") as typeof import("fs");
      const doc = JSON.parse(fsMod.readFileSync(`${outBase}.json`, "utf-8"));
      text = (doc.transcription ?? []).map((seg: any) => String(seg.text ?? "").trim()).join(" ");
    } catch {
      text = res.stdout.split("\n").map((l) => l.trim()).filter(Boolean).join(" ");
    }
    return { text: text.replace(/\s+/g, " ").trim(), avgLogprob };
  }

  /** Transcribe a raw audio Blob/file from capture or phone upload. */
  async transcribeBlob(bytes: Uint8Array, filename: string, initialPrompt?: string): Promise<Transcription> {
    await node("stt");
    const pathMod = require("path") as typeof import("path");
    const osMod = require("os") as typeof import("os");
    const fsMod = require("fs") as typeof import("fs");
    const tmp = pathMod.join(osMod.tmpdir(), `vb-${Date.now()}-${filename.replace(/[^\w.-]/g, "_")}`);
    fsMod.writeFileSync(tmp, Buffer.from(bytes));
    try {
      const wav = await this.decodeToWav(tmp);
      const tr = await this.transcribe(wav, initialPrompt);
      if (wav !== tmp) fsMod.rmSync(wav, { force: true });
      return tr;
    } finally {
      fsMod.rmSync(tmp, { force: true });
    }
  }
}

/** Vault-derived glossary -> whisper --prompt biasing (names/projects stop garbling). */
export function glossaryPrompt(s: VBSettings, app: App): string {
  if (!s.glossaryBiasing) return "";
  const terms = new Set<string>();
  for (const file of app.vault.getMarkdownFiles().slice(0, 200)) {
    const cache = app.metadataCache.getFileCache(file);
    const title = cache?.frontmatter?.title ?? file.basename;
    // Unicode-aware word matching (Cyrillic/Latin/diacritics)
    for (const w of String(title).match(/[\p{L}\p{N}_][\p{L}\p{N}_-]{2,}/gu) ?? []) {
      // skip attachments and machine artifacts — they bias whisper badly
      if (/[~@]|\.(jpg|jpeg|png|raw|pdf|mp4|mov|webp|gif|wav|md)$/i.test(w)) continue;
      if (w[0] === w[0].toUpperCase()) terms.add(w);
    }
    for (const tag of cache?.tags ?? []) terms.add(tag.tag.replace(/^#/, ""));
    if (terms.size > 60) break;
  }
  if (terms.size === 0) return "";
  return "Vocabulary: " + [...terms].slice(0, 60).join(", ") + ".";
}

// (App type re-exported for late importers)
export type { App };
