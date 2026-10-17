/** Daily Journal route: "log this: ..." -> timestamped append + implicit stat tags. */

import { TFile, normalizePath } from "obsidian";
import { journalEnrich } from "../prompts";
import type { BrainDeps } from "../brain";
import { RouteResult } from "../brain";
import { dailyJournalNote, journalEntry } from "../templates";
import { parseFrontmatter, serializeFrontmatter, todayISO } from "../util";

export async function handleJournal(d: BrainDeps, entryText: string, ts: number): Promise<RouteResult> {
  const now = new Date(ts);
  const date = todayISO(now);
  const path = normalizePath(`${d.settings.journalFolder}/${date}.md`);

  // optional enrichment — must never block the write
  let heading = "Log";
  let tags: string[] = [];
  try {
    const doc = await d.ollama.generate(journalEnrich(entryText), { json: true });
    heading = String(doc?.heading ?? "Log").slice(0, 60) || "Log";
    tags = Array.isArray(doc?.tags) ? doc.tags.slice(0, 8).map(String) : [];
  } catch {
    /* LLM down or bad JSON — degrade gracefully */
  }

  let file = d.app.vault.getAbstractFileByPath(path);
  const existed = file instanceof TFile;
  const prior = file instanceof TFile ? await d.app.vault.read(file) : null;

  if (!existed) {
    const pretty = now.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
    await d.app.vault.create(path, dailyJournalNote(date, pretty));
    file = d.app.vault.getAbstractFileByPath(path);
  }
  if (!(file instanceof TFile)) {
    return { state: "error", title: "❌ Journal write failed", body: path };
  }

  const entry = journalEntry(now, heading, tags, entryText);
  await d.app.vault.process(file, (text) => {
    // bump entry_count in frontmatter, then append the new section
    const { fm, body } = parseFrontmatter(text);
    fm.entry_count = Number(fm.entry_count ?? 0) + 1;
    return serializeFrontmatter(fm) + body.replace(/^\n+/, "").replace(/\s+$/, "") + "\n\n" + entry;
  });
  await d.ledger.record(`journal entry: ${heading}`, [[path, prior]]);
  return { state: "journal", title: "📝 Logged", body: path };
}
