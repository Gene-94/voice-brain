/** Stats generator: collect -> precompute (code) -> Gemma extracts (deep lane) -> validate -> write. */

import { TFile, normalizePath } from "obsidian";
import { PROMPT_VERSIONS, creativeAssess, statsV1 } from "../prompts";
import type { BrainDeps } from "../brain";
import { RouteResult } from "../brain";
import { validateStats } from "../schemata/stats";
import { precomputeBlock } from "../insights";
import { parseFrontmatter, todayISO } from "../util";

export async function handleStats(d: BrainDeps, ts: number, dayOverride?: string): Promise<RouteResult> {
  const now = new Date(ts);
  const day = dayOverride ?? todayISO(now);

  // ---- collect today's inputs
  const blocks: string[] = [];
  const journalPath = normalizePath(`${d.settings.journalFolder}/${day}.md`);
  const journalFile = d.app.vault.getAbstractFileByPath(journalPath);
  let journalWords = 0;
  if (journalFile instanceof TFile) {
    const { body } = parseFrontmatter(await d.app.vault.read(journalFile));
    journalWords = body.split(/\s+/).filter(Boolean).length;
    blocks.push(`[${journalPath}]\n${body.slice(0, 4000).trim()}`);
  }
  for (const file of d.app.vault.getMarkdownFiles()) {
    if (file.parent?.path !== d.settings.dreamFolder || !file.basename.startsWith(day)) continue;
    blocks.push(`[${file.path}]\n${(await d.app.vault.cachedRead(file)).slice(0, 800).trim()}`);
  }
  const entriesCtx = blocks.join("\n\n") || "(no dream or journal entries today)";

  // ---- creative output scan (notes created today outside managed folders)
  const managed = new Set([d.settings.dreamFolder, d.settings.journalFolder,
                           d.settings.statsFolder, d.settings.inboxFolder]);
  const creative: any[] = [];
  for (const file of d.app.vault.getMarkdownFiles()) {
    if (managed.has(file.parent?.path ?? "")) continue;
    const cache = d.app.metadataCache.getFileCache(file);
    const created = String(cache?.frontmatter?.created_at ?? "");
    if (!created.startsWith(day)) continue;
    const body = await d.app.vault.cachedRead(file);
    const words = body.split(/\s+/).filter(Boolean).length;
    if (words < 10) continue;
    const links = d.app.metadataCache.getFileCache(file)?.links?.length ?? 0;
    creative.push({ rel: file.path, body: body.slice(0, 600), words,
                    connectivity: Math.min(10, links * 2 + 1) });
  }

  let creativeBlock: any = {
    notes_created_count: creative.length,
    notes_created_today: creative.map((c) => c.rel),
    total_words_produced: creative.reduce((a, c) => a + c.words, 0),
    creativity_score_unit: "0-100",
    source: "Vault filesystem scan + Gemma assessment",
    prompt_version: PROMPT_VERSIONS.creative_assess,
    notes: "No creative notes produced today.",
    novelty_average: 0, depth_average: 0, connectivity_average: 0,
    clarity_average: 0, actionability_average: 0, creativity_score: 0,
  };
  if (creative.length) {
    let quality = { novelty: 0, depth: 0, clarity: 0, actionability: 0 };
    try {
      const ctx = creative.map((c) => `[${c.rel}]\n${c.body}`).join("\n\n");
      const doc = await d.ollama.generate(creativeAssess(ctx), { lane: "deep", json: true });
      const byRel = new Map<any, any>((doc?.assessments ?? []).map((a: any) => [a.rel, a]));
      for (const c of creative) {
        const a = byRel.get(c.rel) ?? {};
        for (const dim of Object.keys(quality)) {
          const v = Number(a[dim]);
          if (v >= 0 && v <= 10) quality = { ...quality, [dim]: quality[dim as keyof typeof quality] + v };
        }
      }
      const n = creative.length;
      const connAvg = Math.round((creative.reduce((a, c) => a + c.connectivity, 0) / n) * 10) / 10;
      creativeBlock = {
        ...creativeBlock,
        novelty_average: Math.round((quality.novelty / n) * 10) / 10,
        depth_average: Math.round((quality.depth / n) * 10) / 10,
        clarity_average: Math.round((quality.clarity / n) * 10) / 10,
        actionability_average: Math.round((quality.actionability / n) * 10) / 10,
        connectivity_average: connAvg,
        creativity_score: Math.round(((quality.novelty + quality.depth + quality.clarity
          + quality.actionability) / n / 4 + connAvg / 10) / 2 * 100),
        notes: `${n} notes, ${creativeBlock.total_words_produced} words. Connectivity ${connAvg}/10 (deterministic link count).`,
      };
    } catch {
      creativeBlock.notes = "LLM quality assessment unavailable — deterministic counts only.";
    }
  }

  // ---- history for trends/correlations (deterministic)
  const history: any[] = [];
  const statDays = new Set<string>();
  const journalDays = new Set<string>();
  for (let i = 1; i <= d.settings.statsHistoryDays; i++) {
    const past = new Date(new Date(day + "T00:00:00").getTime() - i * 86400_000).toISOString().slice(0, 10);
    const f = d.app.vault.getAbstractFileByPath(normalizePath(`${d.settings.statsFolder}/${past}.json`));
    if (f instanceof TFile) {
      try {
        history.push(JSON.parse(await d.app.vault.read(f)));
        statDays.add(past);
      } catch { /* skip corrupted */ }
    }
    if (d.app.vault.getAbstractFileByPath(normalizePath(`${d.settings.journalFolder}/${past}.md`))) {
      journalDays.add(past);
    }
  }
  statDays.add(day);
  const precomputed = precomputeBlock(
    null, history, journalWords, Number(creativeBlock.total_words_produced ?? 0),
    statDays, journalDays, day);

  // ---- deep lane generation
  const doc = await d.ollama.generate(
    statsV1(day, entriesCtx, JSON.stringify(creativeBlock, null, 1),
            JSON.stringify(history.map((h) => ({ date: h.date, derived: h.derived }))).slice(0, 6000) || "(no history)",
            JSON.stringify(precomputed, null, 1)),
    { lane: "deep", json: true, validator: validateStats });

  // authority fields set by code, not the LLM:
  const final = {
    ...doc,
    date: day,
    generated_at: now.toISOString().slice(0, 19),
    schema_version: "1.0.0",
    generated_by: {
      model: d.ollama.lane("deep").model,
      prompt_version: PROMPT_VERSIONS.stats_v1,
      temperature: d.settings.temperatureDeep,
    },
  };
  if (final.insights && typeof final.insights === "object") final.insights.correlations = precomputed.correlations;
  if (final.derived && typeof final.derived === "object") final.derived.trending = precomputed.trend.trending;

  const outPath = normalizePath(`${d.settings.statsFolder}/${day}.json`);
  const existing = d.app.vault.getAbstractFileByPath(outPath);
  const prior = existing instanceof TFile ? await d.app.vault.read(existing) : null;
  const content = JSON.stringify(final, null, 2) + "\n";
  if (existing instanceof TFile) await d.app.vault.modify(existing, content);
  else await d.app.vault.create(outPath, content);
  await d.ledger.record(`stats generated for ${day}`, [[outPath, prior]]);

  return {
    state: "stats",
    title: "📊 Stats generated",
    body: `Readiness: ${final.derived?.readiness_score ?? "—"}/100 | Wellbeing: ${final.derived?.wellbeing_index ?? "—"}/10\n${outPath}`,
  };
}
