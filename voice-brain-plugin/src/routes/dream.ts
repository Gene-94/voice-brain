/** Dream Journal route: "I had a dream..." -> one note per dream, with theme connections. */

import { TFile, normalizePath } from "obsidian";
import { PROMPT_VERSIONS, dreamSplit } from "../prompts";
import type { BrainDeps } from "../brain";
import { RouteResult } from "../brain";
import { dateStampedName, dreamNote } from "../templates";
import { parseFrontmatter, todayISO } from "../util";

function validateDreams(doc: any): string[] {
  const errors: string[] = [];
  if (typeof doc !== "object" || !Array.isArray(doc?.dreams)) return ["top-level object must contain 'dreams' list"];
  doc.dreams.forEach((d: any, i: number) => {
    if (typeof d !== "object") return errors.push(`dreams[${i}] must be an object`);
    if (!String(d?.title ?? "").trim()) errors.push(`dreams[${i}].title is empty`);
    if (!String(d?.narration ?? "").trim()) errors.push(`dreams[${i}].narration is empty`);
    const v = d?.vividness;
    if (typeof v !== "number" || v < 1 || v > 10) errors.push(`dreams[${i}].vividness must be 1-10`);
  });
  return errors;
}

export async function handleDream(d: BrainDeps, narration: string, ts: number): Promise<RouteResult> {
  const doc = await d.ollama.generate(dreamSplit(narration), { json: true, validator: validateDreams });
  const dreams: any[] = doc?.dreams ?? [];
  if (!dreams.length) {
    return { state: "error", title: "🤔 Not a dream?", body: "Nothing dream-like found in that." };
  }

  const now = new Date(ts);
  const date = todayISO(now);

  // recurring-theme connections from the existing dream index (code, not LLM)
  const themeOwners = new Map<string, string[]>();
  for (const file of d.app.vault.getMarkdownFiles()) {
    if (file.parent?.path !== d.settings.dreamFolder) continue;
    const cache = d.app.metadataCache.getFileCache(file);
    const themes: string[] = Array.isArray(cache?.frontmatter?.themes) ? cache.frontmatter.themes : [];
    for (const t of themes) {
      const key = String(t).toLowerCase();
      themeOwners.set(key, [...(themeOwners.get(key) ?? []), file.basename]);
    }
  }

  const created: string[] = [];
  const ops: Array<[string, string | null]> = [];
  for (let i = 0; i < dreams.length; i++) {
    const dream = dreams[i];
    const title = String(dream.title).trim();
    const themes = (dream.themes ?? []).slice(0, 6).map(String);
    const connections = themes
      .flatMap((t: string) => (themeOwners.get(t.toLowerCase()) ?? []).map((stem: string) =>
        `- Recurring theme **${t}**: see also [[${stem}]]`))
      .filter((v: string, idx: number, arr: string[]) => arr.indexOf(v) === idx)
      .slice(0, 4);
    const content = dreamNote({
      date, seq: i + 1, recordedAt: now, title,
      vividness: Math.max(1, Math.min(10, Math.round(Number(dream.vividness ?? 5)))),
      lucidity: Boolean(dream.lucidity),
      themes, emotionalTone: String(dream.emotional_tone ?? "unclear"),
      narration: String(dream.narration ?? narration).trim(),
      summary: String(dream.summary ?? "").trim(),
      connections: connections.length ? connections.join("\n")
        : "- First appearance of these themes in your dream journal.",
      model: d.ollama.lane("quick").model,
    });
    const path = normalizePath(dateStampedName(d.settings.dreamFolder, date, title));
    const unique = await uniquePath(d, path);
    await d.app.vault.create(unique, content);
    created.push(unique);
    ops.push([unique, null]);
  }
  await d.ledger.record(`dream session: ${created.length} dream(s) captured`, ops);
  return {
    state: "dream",
    title: `💜 ${created.length} dream${created.length > 1 ? "s" : ""} saved`,
    body: created.join("\n"),
  };
}

async function uniquePath(d: BrainDeps, path: string): Promise<string> {
  let candidate = path;
  let n = 2;
  while (d.app.vault.getAbstractFileByPath(candidate)) {
    candidate = path.replace(/(\.[^.]+)$/, `-${n++}$1`);
  }
  return candidate;
}
