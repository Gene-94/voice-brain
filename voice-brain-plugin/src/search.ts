/** Vault search — deterministic TF over the metadata cache. No vector DB, no embeddings. */

import { TFile, type App } from "obsidian";

export interface SearchHit {
  file: TFile;
  score: number;
}

export function noteTitle(app: App, file: TFile): string {
  const cache = app.metadataCache.getFileCache(file);
  const fmTitle = cache?.frontmatter?.title;
  if (fmTitle) return String(fmTitle);
  return file.basename;
}

export async function searchVault(app: App, query: string, k = 6): Promise<SearchHit[]> {
  const terms = query.toLowerCase().match(/[\p{L}\p{N}]{3,}/gu) ?? [];  // Unicode: pt/ru/cyrillic
  if (terms.length === 0) return [];
  const hits: SearchHit[] = [];
  for (const file of app.vault.getMarkdownFiles()) {
    const cache = app.metadataCache.getFileCache(file);
    const title = noteTitle(app, file).toLowerCase();
    let score = 0;
    for (const term of terms) {
      score += 3 * countOccurrences(title, term);
      const tags = (cache?.tags ?? []).map((t) => t.tag.toLowerCase());
      if (tags.some((t) => t.includes(term))) score += 2;
    }
    if (score > 0) {
      hits.push({ file, score });
      continue;
    }
    // body scan only for candidates that failed title/tag scoring (cheap enough at vault scale)
    const body = (await app.vault.cachedRead(file)).toLowerCase();
    let bodyScore = 0;
    for (const term of terms) bodyScore += countOccurrences(body, term);
    if (bodyScore > 0) hits.push({ file, score: bodyScore });
  }
  hits.sort((a, b) => b.score - a.score);
  return hits.slice(0, k);
}

function countOccurrences(haystack: string, needle: string): number {
  if (!needle) return 0;
  let count = 0;
  let idx = haystack.indexOf(needle);
  while (idx !== -1) {
    count++;
    idx = haystack.indexOf(needle, idx + needle.length);
  }
  return count;
}
