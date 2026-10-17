/** The Brain: one place that routes any utterance (hotkey, phone, in-app, spool)
 *  to a vault action. The LLM narrates; code calculates; nothing is ever lost. */

import { Notice, TFile, normalizePath, type App } from "obsidian";
import { Kind, classify, classifyWithPatterns, END_DICTATION } from "./intent";
import { Ledger } from "./ledger";
import { Patterns } from "./patterns";
import { LLMError, Ollama } from "./llm";
import { Stt, glossaryPrompt } from "./stt";
import * as templates from "./templates";
import { PROMPT_VERSIONS, intentClassify, briefMe } from "./prompts";
import type { VBSettings, Utterance } from "./types";
import { hhmm, parseFrontmatter, serializeFrontmatter, slugify, todayISO } from "./util";
import { searchVault } from "./search";
import { handleDream } from "./routes/dream";
import { handleJournal } from "./routes/journal";
import { handleNoteCreate, handleCapture, handlePolishedNote, saveTranscriptNote } from "./routes/notes";
import { handleQuery } from "./routes/query";
import { handleStats } from "./routes/stats";
import { DictationState } from "./dictation";

export interface RouteResult {
  state: string; // statusbar icon state
  title: string;
  body: string;
}

export interface BrainDeps {
  app: App;
  settings: VBSettings;
  ollama: Ollama;
  ledger: Ledger;
  stt: Stt;
}

export class Brain {
  dictation = new DictationState();
  lastResult = "—";
  patterns: Patterns;

  constructor(private d: BrainDeps) {
    this.patterns = new Patterns(d.app, d.settings);
  }

  get app(): App { return this.d.app; }
  get s(): VBSettings { return this.d.settings; }
  get ollama(): Ollama { return this.d.ollama; }
  get ledger(): Ledger { return this.d.ledger; }
  get stt(): Stt { return this.d.stt; }

  /** Entry point for every utterance from every source. Never throws. */
  async routeUtterance(u: Utterance): Promise<RouteResult> {
    const text = (u.text ?? "").trim();
    if (!text) return { state: "timeout", title: "Nothing heard", body: "" };

    if (this.dictation.active && END_DICTATION.some((e) => text.toLowerCase().startsWith(e))) {
      this.dictation.stop();
      return { state: "success", title: "🎙️ Dictation ended", body: text };
    }

    // user patterns (the vault file) take priority over the built-ins
    const intent = (await classifyWithPatterns(text, this.patterns)) ?? classify(text);
    // raw whisper transcript -> Voice Brain Inbox, before any LLM runs
    // (survives LLM failures and undo — never lose input)
    await saveTranscriptNote(this.d, u, intent.kind);
    try {
      switch (intent.kind) {
        case Kind.Dream:
          return await handleDream(this.d, intent.payload || intent.text, u.ts);
        case Kind.Scratch:
          return { state: "success", title: "🔄 Undone", body: await this.ledger.undoLast() };
        case Kind.Journal:
        case Kind.StatLog:
          return await handleJournal(this.d, intent.payload || intent.text, u.ts);
        case Kind.Note:            // "I have an idea …" -> polished note in Projects
          return await handlePolishedNote(this.d, intent.payload || intent.text, u.ts, intent.folder);
        case Kind.Capture:
          return await handleCapture(this.d, intent.payload || intent.text, u.ts);
        case Kind.Stats:
          return await handleStats(this.d, u.ts);
        case Kind.Brief:
          return { state: "query", title: "🌅 Briefing", body: await this.brief() };
        case Kind.Dictation:
          this.dictation.start();
          return { state: "success", title: "🎙️ Dictation started", body: "Speak freely — 'end dictation' stops." };
        case Kind.General: {
          const doc = await this.ollama.generate(intentClassify(text), { json: true });
          const kind = String(doc?.kind ?? "capture");
          if (kind === "create_note") return await handleNoteCreate(this.d, text, u.ts);
          if (kind === "query") return { state: "query", title: "💬 Answer", body: await this.query(text) };
          // unknown utterance -> polished capture into the inbox (raw kept at bottom)
          return await handlePolishedNote(this.d, text, u.ts);
        }
      }
    } catch (e: any) {
      // never lose input: verbatim capture + loud error
      try {
        const res = await handleCapture(this.d, text, u.ts);
        return { state: "error", title: "❌ Something went wrong",
                 body: `${String(e?.message ?? e)}\nWords saved to ${res.body}` };
      } catch {
        return { state: "error", title: "❌ Something went wrong", body: String(e?.message ?? e) };
      }
    }
    return { state: "error", title: "unreachable", body: "" };
  }

  async query(question: string): Promise<string> {
    return handleQuery(this.d, question);
  }

  async brief(): Promise<string> {
    const yesterday = new Date(Date.now() - 86400_000).toISOString().slice(0, 10);
    let statsCtx = "(no stats generated yesterday)";
    const yFile = this.app.vault.getAbstractFileByPath(
      normalizePath(`${this.s.statsFolder}/${yesterday}.json`));
    if (yFile instanceof TFile) statsCtx = (await this.app.vault.read(yFile)).slice(0, 3000);
    let todos = 0;
    for (const f of this.app.vault.getMarkdownFiles()) {
      const body = await this.app.vault.cachedRead(f);
      todos += (body.match(/^\s*- \[ \] /gm) ?? []).length;
    }
    const streak = this.captureStreak();
    try {
      return String(await this.ollama.generate(briefMe(statsCtx, todos, streak), { lane: "quick" }));
    } catch {
      // deterministic fallback — a briefing must never fail entirely
      const lines = [`🌅 Good morning. Open TODOs: ${todos}.`, `Capture streak: ${streak} days.`];
      if (yFile instanceof TFile) {
        try {
          const doc = JSON.parse(await this.app.vault.read(yFile));
          lines.splice(1, 0, `Yesterday's readiness: ${doc.derived?.readiness_score ?? "—"}/100.`);
          const rec = doc.derived?.recommendations?.[0]?.action;
          if (rec) lines.push(`💡 ${rec}`);
        } catch { /* corrupted json — ignore */ }
      }
      return lines.join("\n");
    }
  }

  captureStreak(): number {
    const days = new Set<string>();
    for (const f of this.app.vault.getMarkdownFiles()) {
      const m = f.basename.match(/^(\d{4}-\d{2}-\d{2})/);
      if (m && (f.parent?.path === this.s.journalFolder || f.parent?.path === this.s.dreamFolder)) {
        days.add(m[1]);
      }
    }
    let streak = 0;
    const d = new Date();
    while (days.has(d.toISOString().slice(0, 10))) {
      streak++;
      d.setDate(d.getDate() - 1);
    }
    return streak;
  }
}
