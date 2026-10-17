/** Note creation + the capture-everything safety net (never calls the LLM on capture). */

import { normalizePath } from "obsidian";
import { PROMPT_VERSIONS, noteDraft, polishNote } from "../prompts";
import type { BrainDeps } from "../brain";
import { RouteResult } from "../brain";
import { dateStampedName, inboxNote, render } from "../templates";
import { hhmm, todayISO, serializeFrontmatter } from "../util";

function validateNote(doc: any): string[] {
  if (typeof doc !== "object") return ["must be an object"];
  if (!String(doc?.title ?? "").trim()) return ["'title' is required"];
  if (!String(doc?.content ?? "").trim()) return ["'content' is required"];
  return [];
}

export async function handleNoteCreate(d: BrainDeps, spokenIntent: string, ts: number): Promise<RouteResult> {
  const doc = await d.ollama.generate(noteDraft(spokenIntent), { json: true, validator: validateNote });
  const now = new Date(ts);
  const title = String(doc.title).trim();
  const tags = (doc.tags ?? []).slice(0, 4).map((t: any) => String(t).replace(/^#/, "").toLowerCase());
  const content = String(doc.content).trim();

  const note = inboxNote(now, title, tags, `# ${title}\n\n${content}`, {
    prompt_version: PROMPT_VERSIONS.note_draft,
  });
  const path = normalizePath(dateStampedName(d.settings.inboxFolder, todayISO(now), title));
  await d.app.vault.create(path, note);
  await d.ledger.record(`note created: ${title}`, [[path, null]]);
  return { state: "note", title: "🗒️ Note created", body: path };
}

/** Every utterance lands VERBATIM in the Voice Brain Inbox before any LLM runs.
 *  Not in the undo ledger — your words survive LLM failures and "scratch that". */
export async function saveTranscriptNote(
  d: BrainDeps,
  u: { text: string; source: string; ts: number; confidence?: number | null },
  route: string,
): Promise<void> {
  try {
    const now = new Date(u.ts);
    const folder = normalizePath(d.settings.inboxFolder);
    if (!d.app.vault.getAbstractFileByPath(folder)) {
      await d.app.vault.createFolder(folder);
    }
    const hhmm = (x: number) => String(x).padStart(2, "0");
    const stamp = `${hhmm(now.getHours())}${hhmm(now.getMinutes())}${hhmm(now.getSeconds())}`;
    const fm = serializeFrontmatter({
      title: `Transcript ${hhmm(now.getHours())}:${hhmm(now.getMinutes())}`,
      tags: ["transcript"],
      created_at: now.toISOString().slice(0, 19),
      created_by: "voice-brain",
      source: u.source,
      route,
      confidence: u.confidence ?? null,
    });
    const path = normalizePath(`${folder}/${todayISO(now)}_transcript-${stamp}.md`);
    if (!d.app.vault.getAbstractFileByPath(path)) {
      await d.app.vault.create(path,
        `${fm}\n# Transcript ${hhmm(now.getHours())}:${hhmm(now.getMinutes())}\n\n${u.text.trim()}\n`);
    }
  } catch (e) {
    console.warn(`[voice-brain] raw transcript save failed: ${e}`);
  }
}

/** Raw transcript -> polished note (bullets, structure) into an arbitrary folder.
 *  The raw transcript is preserved at the bottom — never lose input. */
export async function handlePolishedNote(d: BrainDeps, rawText: string, ts: number,
                                        folder?: string): Promise<RouteResult> {
  const doc = await d.ollama.generate(polishNote(rawText), { json: true, validator: validateNote });
  const now = new Date(ts);
  const title = String(doc.title).trim();
  const tags = (doc.tags ?? []).slice(0, 4).map((t: any) => String(t).replace(/^#/, ""));
  const content = String(doc.content).trim();

  const dest = normalizePath(folder ?? d.settings.inboxFolder);
  if (!d.app.vault.getAbstractFileByPath(dest)) {
    await d.app.vault.createFolder(dest);
  }
  const fm = serializeFrontmatter({
    title, tags: tags.length ? tags : ["capture"],
    created_at: now.toISOString().slice(0, 19),
    created_by: "voice-brain",
    prompt_version: PROMPT_VERSIONS.polish_note,
  });
  const path = normalizePath(dateStampedName(dest, todayISO(now), title));
  let unique = path;
  let n = 2;
  while (d.app.vault.getAbstractFileByPath(unique)) {
    unique = path.replace(/(\.[^.]+)$/, `-${n++}$1`);
  }
  await d.app.vault.create(unique, `${fm}\n# ${title}\n\n${content}\n`);
  await d.ledger.record(`polished note: ${title}`, [[unique, null]]);
  return { state: "note", title: "🗒️ Note captured", body: unique };
}

export async function handleCapture(d: BrainDeps, rawText: string, ts: number): Promise<RouteResult> {
  const now = new Date(ts);
  const title = `Capture ${hhmm(ts)}`;
  const note = inboxNote(now, title, ["capture"], `# ${title}\n\n${rawText.trim()}\n`);
  const path = normalizePath(
    `${d.settings.inboxFolder}/${todayISO(now)}_capture-${now.toISOString().slice(11, 19).replace(/:/g, "")}.md`);
  await d.app.vault.create(path, note);
  await d.ledger.record("verbatim capture", [[path, null]]);
  return { state: "success", title: "📥 Saved to inbox", body: path };
}

export { render };
