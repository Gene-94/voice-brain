/** All LLM prompts, versioned (stamped into outputs for traceability). */

export const PROMPT_VERSIONS = {
  dream_split: "1.0.0",
  journal_enrich: "1.0.0",
  intent_classify: "1.0.0",
  note_draft: "1.0.0",
  polish_note: "1.0.0",
  query_answer: "1.0.0",
  creative_assess: "1.0.0",
  stats_v1: "1.0.0",
  brief_me: "1.0.0",
} as const;

export function polishNote(transcript: string): string {
  return (
    "You clean up a RAW voice transcript into a well-formed Obsidian note.\n" +
    "Rules:\n" +
    "- Preserve the speaker's meaning EXACTLY — restructure, never invent or drop content.\n" +
    "- Fix speech artifacts: filler words (um, uh, like), false starts, repetitions.\n" +
    "- Structure with Markdown: a clear opening line, then bullet points for distinct\n" +
    "  thoughts. Keep the speaker's reasoning order visible.\n" +
    "- title: a short clean note title (not a sentence).\n" +
    "- content: the formatted Markdown body (no H1 heading — the template adds it).\n" +
    "- tags: 1-4 lowercase topical tags.\n\n" +
    LANG_RULE + "\n" +
    'Return ONLY valid JSON: {"title": "...", "content": "...", "tags": ["..."]}\n\n' +
    "Raw transcript:\n" +
    '"""\n' + transcript + '\n"""\n'
  );
}

const LANG_RULE =
  "ALWAYS respond in the SAME LANGUAGE the user spoke — English, Portuguese, or Russian. " +
  "NEVER translate: if the user wrote in Russian, every text you produce (headings, notes, " +
  "tags aside) must be in Russian; if in Portuguese, in Portuguese; if in English, in English.";

export function dreamSplit(narration: string): string {
  return `You are a dream analysis parser. The user narrated one or more dreams.
Split the narration into INDIVIDUAL dreams. For each dream return:
- title: evocative 3-6 word title
- summary: 1-2 sentence description
- narration: the user's own words for this dream, lightly cleaned of speech artifacts, meaning preserved
- themes: list of 2-6 symbolic themes (lowercase single words)
- emotional_tone: dominant emotion or mix
- vividness: 1-10 integer
- lucidity: true/false (dreamer aware it was a dream?)

${LANG_RULE}
Return ONLY valid JSON: {"dreams": [{...}, ...]}
If there is exactly one dream, return a list with one element. If the text is not about a dream at all, return {"dreams": []}.

User narration:
"""${narration}"""`;
}

export function journalEnrich(entryText: string): string {
  return `You tag a journal entry for a quantified-self pipeline.
The heading MUST be written in the same language as the entry text (never translate it).
Analyze this journal entry and return:
- heading: short 2-5 word label for the entry (like a section title)
- tags: list of lightweight structured stat tags, each formatted "category=value".
  Allowed categories: mood (0-10), energy (0-10), food:<desc>, sleep, exercise, social, caffeine, pain, focus.
  Only include tags actually supported by the text. Empty list if none.

${LANG_RULE}
Return ONLY valid JSON: {"heading": "...", "tags": ["mood=8", ...]}

Journal entry:
"""${entryText}"""`;
}

export function intentClassify(text: string): string {
  return `Classify the user's voice command for a personal knowledge assistant.
Categories:
- create_note: the user wants a new note created/drafted
- query: the user asks a question about their knowledge/notes ("what do I know about...")
- capture: anything else — save the words verbatim as a capture

${LANG_RULE}
Return ONLY valid JSON: {"kind": "create_note|query|capture", "reason": "one short line"}

Command:
"""${text}"""`;
}

export function noteDraft(text: string): string {
  return `Draft a well-structured Obsidian Markdown note from the user's spoken intent.
Return:
- title: clean note title (not the raw voice text)
- content: the note body in Markdown. Expand sensibly on what the user said — structure with
  headings/lists where useful — but DO NOT invent facts the user didn't state.
- tags: 1-4 lowercase tags

${LANG_RULE}
Return ONLY valid JSON: {"title": "...", "content": "markdown...", "tags": ["..."]}

User intent:
"""${text}"""`;
}

export function queryAnswer(question: string, notesCtx: string): string {
  return `You answer questions over the user's personal knowledge vault (Obsidian notes).
Rules:
- Answer ONLY from the provided notes. If they don't contain the answer, say so plainly.
- Cite sources inline as [[Note Name]] wikilinks wherever you use a note.
- Be concise: 3-8 sentences or a short list.
${LANG_RULE}

Question: ${question}

Notes:
"""${notesCtx}"""`;
}

export function creativeAssess(notesCtx: string): string {
  return `Assess the user's creative output for the day — notes they produced.
For EACH note return:
- rel: the note's path exactly as given
- novelty, depth, clarity, actionability: 0-10 integers
- domain: one lowercase tag (programming, writing, design, research, personal, ...)
- format: one lowercase tag (note, essay, spec, todo, idea_capture, meeting_notes, moc, ...)
Do NOT assess connectivity — that is computed deterministically elsewhere.

${LANG_RULE}
Return ONLY valid JSON: {"assessments": [{...}, ...]} — one entry per note, same order.

Notes (path, then content, truncated):
"""${notesCtx}"""`;
}

export function statsV1(day: string, entriesCtx: string, creativeBlock: string,
                        historyCtx: string, precomputed: string): string {
  return `You are a Quantified Self analysis engine. Analyze the user's entries from ${day}
and produce a JSON document conforming to the Voice Brain Stats Schema v1.0.0.

RULES:
1. Return ONLY valid JSON.
2. All scores are integers (0-100 for computed scores, 0-10 for subjective ratings) or null.
3. Every category (sleep, mood, energy, physical, nutrition, cognitive, creative_output, social,
   environment, habits, time_use) MUST appear with a "notes" field of 1-3 sentences and a "source" string.
4. Missing information = null. NEVER hallucinate values.
5. The "narrative" field (inside "insights") tells the day's human story in 2-3 sentences.
6. "derived" must contain: readiness_score (0-100), wellbeing_index (0-10), day_type, archetype
   (an evocative name like "The Recovering Optimizer"), and "recommendations": a list of
   {"priority": int, "category": str, "action": str, "rationale": str, "confidence": 0-1} —
   rationale must cite specific evidence from the entries.
7. Use the PRECOMPUTED numbers (correlations, trends, deltas) exactly as given when writing
   "insights.correlations" and trend text — do not invent or recompute statistics.
8. ${LANG_RULE} — except JSON keys and category names, which stay in English.

TODAY'S ENTRIES:
"""${entriesCtx}"""

CREATIVE OUTPUT (precomputed assessment — use as-is for the creative_output block):
"""${creativeBlock}"""

HISTORY (last ${"7"} days of stats, for trend context):
"""${historyCtx}"""

PRECOMPUTED NUMBERS (authoritative — do not alter):
"""${precomputed}"""`;
}

export function briefMe(statsCtx: string, todos: number, streak: number): string {
  return `Generate a 60-second personal morning briefing from yesterday's stats.
Format as a short spoken script (3-5 sentences), friendly and honest.
Mention: sleep, mood/energy highlights, the single top recommendation, and open TODOs (${todos} open).
Capture streak: ${streak} days.

${LANG_RULE}
Return plain text (no markdown headings), max 90 words.

Stats:
"""${statsCtx}"""`;
}
