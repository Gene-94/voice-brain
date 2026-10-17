/** User-editable trigger patterns — the SAME vault note the daemon reads
 *  (Settings/voice-brain patterns.md), so editing on any device (LiveSync!)
 *  changes routing everywhere. One source of truth.
 *
 *  Line format: <pattern> | <route> [, <folder>]  — first match wins. */

import { normalizePath, type App } from "obsidian";
import type { VBSettings } from "./types";

export const PATTERNS_PATH = "Voice Brain Settings/patterns.md";

export type Route = "dream" | "journal" | "note" | "capture" | "query" | "stats" | "brief" | "scratch";

export interface PatternRule {
  pattern: string;
  route: Route;
  folder?: string;
  test: (text: string) => RegExpMatchArray | null;
}

const VALID: Route[] = ["dream", "journal", "note", "capture", "query", "stats", "brief", "scratch"];

export const DEFAULT_PATTERNS = `# Voice Brain — trigger patterns

Edit on any device — LiveSync keeps this file in sync everywhere.
Each line:  <pattern> | <route> | <optional folder>
The note is written from what you said MINUS the pattern.
Routes: dream, journal, note, capture, query, stats, brief.
First matching line wins.

# Built-ins — English (edit or reorder freely)
I had a dream|dream
I dreamed about|dream
in my dream|dream
last night I dreamt|dream
there was this dream|dream
I have an idea|note|Projects
I want to start a project|note|Projects
log this|journal
log that|journal
journal this|journal
remember this|journal
generate stats|stats
how was my day|stats
analyze my week|stats
brief me|brief
scratch that|scratch

# Português (Portugal)
tive um sonho|dream
sonhei (que|com)|dream
no meu sonho|dream
tive um pesadelo|dream
tenho uma ideia|note|Projects
quero começar um projeto|note|Projects
anota isto|journal
anota isso|journal
regista isto|journal
lembra-te disto|journal
gera as estatísticas|stats
como foi o meu dia|stats
analisa a minha semana|stats
resume-me o dia|brief
esquece isso|scratch

# Русский
мне снился сон|dream
мне приснился сон|dream
во сне|dream
у меня есть идея|note|Projects
у меня идея|note|Projects
есть идея|note|Projects
хочу начать проект|note|Projects
запиши это|journal
запиши|journal
сделай заметку|journal
сгенерируй статистику|stats
сделай статистику|stats
как прошёл мой день|stats
краткий брифинг|brief
брифинг|brief
забудь это|scratch
`;

export class Patterns {
  private cache: PatternRule[] = [];
  private mtime = 0;

  constructor(private app: App, private s: VBSettings) {}

  /** Read (creating with defaults if missing) — NEVER throws; a broken vault
   *  layout degrades to built-in triggers instead of breaking the plugin. */
  async rules(): Promise<PatternRule[]> {
    try {
      const path = normalizePath(PATTERNS_PATH);
      let file = this.app.vault.getAbstractFileByPath(path);
      if (!file) {
        await this.app.vault.create(path, DEFAULT_PATTERNS);
        file = this.app.vault.getAbstractFileByPath(path);
      }
      if (!file || !("stat" in file)) return this.cache;
      const mtime = (file as any).stat.mtime;
      if (this.cache.length && mtime === this.mtime) return this.cache;
      this.mtime = mtime;
      this.cache = this.parse(await this.app.vault.read(file as any));
      return this.cache;
    } catch (e) {
      console.warn(`[voice-brain] patterns file unavailable: ${e}`);
      return this.cache;
    }
  }

  parse(text: string): PatternRule[] {
    const rules: PatternRule[] = [];
    for (const raw of text.split("\n")) {
      const line = raw.trim();
      if (!line || line.startsWith("#")) continue;
      const parts = line.split("|").map((p) => p.trim());
      if (parts.length < 2) continue;
      const [pattern, routeStr, folder] = parts;
      if (!VALID.includes(routeStr as Route)) continue;
      try {
        const re = new RegExp(pattern, "i");
        rules.push({
          pattern, route: routeStr as Route, folder: folder || undefined,
          test: (text: string) => re.exec(text),
        });
      } catch {
        // broken regex — skip, never crash routing
      }
    }
    return rules;
  }

  async match(text: string): Promise<{ rule: PatternRule; rest: string } | null> {
    const clean = text.trim();
    for (const rule of await this.rules()) {
      const m = rule.test(clean);
      if (m) {
        return { rule, rest: clean.slice(m[0].length).replace(/^[\s:,-]+/, "") };
      }
    }
    return null;
  }
}
