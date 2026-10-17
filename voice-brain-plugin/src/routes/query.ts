/** Vault Q&A: TF prefilter -> top-K notes -> deep-lane answer with [[wikilink]] citations. */

import { PROMPT_VERSIONS, queryAnswer } from "../prompts";
import type { BrainDeps } from "../brain";
import { noteTitle, searchVault } from "../search";
import { serializeFrontmatter } from "../util";

const NOTE_BUDGET_CHARS = 3600; // ~900 tokens per note

export async function handleQuery(d: BrainDeps, question: string): Promise<string> {
  const hits = await searchVault(d.app, question, 6);
  if (hits.length === 0) {
    return "I couldn't find anything in your vault about that. Try different words, or say it in another language.";
  }
  const blocks: string[] = [];
  for (const hit of hits.slice(0, 6)) {
    const body = (await d.app.vault.cachedRead(hit.file)).slice(0, NOTE_BUDGET_CHARS).trim();
    blocks.push(`### [${noteTitle(d.app, hit.file)}] (path: ${hit.file.path})\n${body}`);
  }
  return String(await d.ollama.generate(queryAnswer(question, blocks.join("\n\n")), { lane: "deep" }));
}

/** Persist a query answer as a note (used by the "save answer" modal action). */
export async function saveAnswer(d: BrainDeps, question: string, answer: string): Promise<string> {
  const fm = serializeFrontmatter({
    title: `Q: ${question.slice(0, 60)}`,
    tags: ["voice-brain", "answer"],
    created_at: new Date().toISOString().slice(0, 19),
    created_by: "voice-brain",
    prompt_version: PROMPT_VERSIONS.query_answer,
  });
  const path = `${d.settings.inboxFolder}/${new Date().toISOString().slice(0, 10)}_answer.md`;
  await d.app.vault.create(path, `${fm}\n# Q: ${question}\n\n${answer}\n`);
  return path;
}
