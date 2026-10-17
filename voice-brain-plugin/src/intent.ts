/** Trigger routing — ported from the Python suite (priority: dream > others > general). */

export enum Kind {
  Dream = "dream",
  Stats = "stats",
  Brief = "brief",
  StatLog = "stat_log",
  Journal = "journal",
  Note = "note",        // user pattern: polished note, optional custom folder
  Capture = "capture",  // user pattern: verbatim capture safety net
  Scratch = "scratch",
  Dictation = "dictation",
  General = "general",
}

interface Trigger {
  kind: Kind;
  re: RegExp;
}

const TRIGGERS: Trigger[] = [
  {
    kind: Kind.Dream,
    re: /^\s*(?:(?:last\s+night\s+)?i\s+(?:just\s+)?(?:had\s+a\s+dream|dream(?:ed|t))|in\s+my\s+dream|there\s+was\s+this\s+dream|tinha\s+um\s+sonho|sonhei\s+que)\b/i,
  },
  { kind: Kind.Scratch, re: /^\s*(scratch\s+that|undo\s+(?:that|last)|forget\s+that)\b/i },
  {
    kind: Kind.Stats,
    re: /^\s*(?:generate|make|create)\s+stats?\b|^\s*how\s+was\s+my\s+day\b|^\s*analyze\s+my\s+week\b/i,
  },
  { kind: Kind.Brief, re: /^\s*brief\s+me\b|^\s*what.?s\s+my\s+(?:status|readiness)\b/i },
  { kind: Kind.StatLog, re: /^\s*(?:log|track)\s+(?:a\s+)?stat\b/i },
  {
    kind: Kind.Journal,
    re: /^\s*(?:log\s+(?:this|that)|journal\s+this|remember\s+this|anota\s+(?:isso|aquilo))\b/i,
  },
  { kind: Kind.Dictation, re: /^\s*(?:start|begin)\s+dictation\b|^\s*dicta(?:tion)?\s+mode\b/i },
];

export interface Intent {
  kind: Kind;
  text: string;
  payload: string;
  folder?: string;   // user-pattern target folder for NOTE routes
}

import type { PatternRule } from "./patterns";

const ROUTE_TO_KIND: Record<string, Kind> = {
  dream: Kind.Dream, journal: Kind.Journal, note: Kind.Note,
  capture: Kind.Capture, query: Kind.General, stats: Kind.Stats,
  brief: Kind.Brief, scratch: Kind.Scratch,
};

/** User patterns (vault file) first — they override the built-ins. */
export async function classifyWithPatterns(
  text: string, patterns: { match(t: string): Promise<{ rule: PatternRule; rest: string } | null> },
): Promise<Intent | null> {
  const hit = await patterns.match(text.trim());
  if (!hit) return null;
  return {
    kind: ROUTE_TO_KIND[hit.rule.route] ?? Kind.General,
    text,
    payload: hit.rest || text,
    folder: hit.rule.folder,
  };
}

export function classify(text: string): Intent {
  const clean = text.trim();
  if (!clean) return { kind: Kind.General, text: clean, payload: clean };
  for (const t of TRIGGERS) {
    const m = t.re.exec(clean);
    if (m) return { kind: t.kind, text: clean, payload: clean.slice(m[0].length).replace(/^[\s:,-]+/, "") };
  }
  return { kind: Kind.General, text: clean, payload: clean };
}

export const END_DICTATION = ["end dictation", "stop dictation", "fim da ditacao"];
