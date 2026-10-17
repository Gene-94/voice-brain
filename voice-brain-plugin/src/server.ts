/** Localhost HTTP server — receives utterances from:
 *   - the Python daemon (global hotkey captures, already transcribed)
 *   - the Android capture app (raw audio — we decode with ffmpeg + whisper here)
 *  Also ingests the daemon's offline spool and Syncthing capture folders.
 *  Pattern proven by the "Local REST API" Obsidian plugin. */

import * as fs from "fs";
import * as http from "http";
import * as path from "path";
import type { Utterance } from "./types";
import { expandTilde } from "./util";

export interface UtteranceHandler {
  (utterance: import("./types").Utterance): Promise<string>;
}

export interface AudioHandler {
  (bytes: Uint8Array, filename: string): Promise<string>;
}

export class CaptureServer {
  private server: http.Server | null = null;

  constructor(
    private port: number,
    private bindHost: string,
    private token: string,
    private onUtterance: UtteranceHandler,
    private onAudio: AudioHandler,
  ) {}

  start(): void {
    if (this.server) return;
    this.server = http.createServer((req, res) => void this.handle(req, res));
    this.server.listen(this.port, this.bindHost);
  }

  stop(): void {
    this.server?.close();
    this.server = null;
  }

  isLocalhost(): boolean {
    return this.bindHost === "127.0.0.1" || this.bindHost === "localhost";
  }

  private authorized(token: string | undefined): boolean {
    if (!this.token) return this.isLocalhost(); // no token => localhost-only binding
    return token === this.token;
  }

  private async handle(req: http.IncomingMessage, res: http.ServerResponse) {
    res.setHeader("Content-Type", "application/json");
    try {
      const url = new URL(req.url ?? "/", "http://localhost");
      const token = req.headers["x-vb-token"] as string | undefined
        ?? url.searchParams.get("token") ?? undefined;

      if (req.method === "GET" && url.pathname === "/health") {
        res.end(JSON.stringify({ ok: true }));
        return;
      }
      if (req.method === "POST" && (url.pathname === "/utterance" || url.pathname === "/api/capture")) {
        if (!this.authorized(token)) {
          res.statusCode = 401;
          res.end(JSON.stringify({ ok: false, error: "bad or missing token" }));
          return;
        }
        const body = await this.readBody(req);
        const summary = await this.dispatch(body, req);
        res.end(JSON.stringify({ ok: true, summary }));
        return;
      }
      res.statusCode = 404;
      res.end(JSON.stringify({ ok: false, error: "not found" }));
    } catch (e: any) {
      res.statusCode = 500;
      res.end(JSON.stringify({ ok: false, error: String(e?.message ?? e) }));
    }
  }

  private dispatch(body: Buffer, req: http.IncomingMessage): Promise<string> {
    const contentType = String(req.headers["content-type"] ?? "");
    if (contentType.includes("application/json")) {
      const doc = JSON.parse(body.toString("utf-8"));
      if (doc.audioBase64) {
        return this.onAudio(Buffer.from(doc.audioBase64, "base64"), String(doc.filename ?? "capture.webm"));
      }
      return this.onUtterance({
        text: String(doc.text ?? ""),
        source: (doc.source ?? "phone") as Utterance["source"],
        ts: Number(doc.ts ?? Date.now()),
        confidence: doc.confidence ?? null,
      });
    }
    // raw audio bytes (Android app simple mode)
    const filename = String(req.headers["x-vb-filename"] ?? `capture-${Date.now()}.m4a`);
    return this.onAudio(new Uint8Array(body), filename);
  }

  private readBody(req: http.IncomingMessage): Promise<Buffer> {
    return new Promise((resolve, reject) => {
      const chunks: Buffer[] = [];
      req.on("data", (c: Buffer) => {
        chunks.push(c);
        if (req.headers["content-length"] && Buffer.concat(chunks).length > 25 * 1024 * 1024) {
          reject(new Error("capture too large (>25MB)"));
          req.destroy();
        }
      });
      req.on("end", () => resolve(Buffer.concat(chunks)));
      req.on("error", reject);
    });
  }
}

/** Ingest the Python daemon's offline spool (one JSON line per unrelayed transcript). */
export async function ingestPending(pendingFile: string, onUtterance: UtteranceHandler): Promise<number> {
  const file = expandTilde(pendingFile);
  if (!fs.existsSync(file)) return 0;
  const lines = fs.readFileSync(file, "utf-8").split("\n").filter(Boolean);
  let processed = 0;
  const remaining: string[] = [];
  for (const line of lines) {
    try {
      const entry = JSON.parse(line);
      await onUtterance({ text: entry.text, source: "spool", ts: entry.epoch ?? Date.now() });
      processed++;
    } catch {
      remaining.push(line); // keep unprocessable lines for manual inspection
    }
  }
  if (remaining.length) fs.writeFileSync(file, remaining.join("\n") + "\n");
  else fs.rmSync(file, { force: true });
  return processed;
}

/** Ingest phone recordings dropped into Syncthing capture folders (offline path). */
export async function ingestCaptureFolders(
  foldersCsv: string,
  onAudio: AudioHandler,
  log: (msg: string) => void,
): Promise<number> {
  const folders = foldersCsv.split(",").map((f) => f.trim()).filter(Boolean).map(expandTilde);
  let processed = 0;
  for (const folder of folders) {
    if (!fs.existsSync(folder)) continue;
    const doneDir = path.join(folder, "processed");
    fs.mkdirSync(doneDir, { recursive: true });
    for (const name of fs.readdirSync(folder)) {
      const full = path.join(folder, name);
      if (!fs.statSync(full).isFile()) continue;
      if (!/\.(wav|m4a|aac|opus|webm|ogg|mp3)$/i.test(name)) continue;
      try {
        const bytes = new Uint8Array(fs.readFileSync(full));
        await onAudio(bytes, name);
        fs.renameSync(full, path.join(doneDir, `${Date.now()}-${name}`));
        processed++;
      } catch (e: any) {
        log(`capture ingest failed for ${name}: ${e?.message ?? e}`);
      }
    }
  }
  return processed;
}
