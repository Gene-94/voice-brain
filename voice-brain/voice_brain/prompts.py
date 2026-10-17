"""All LLM prompts, versioned. Every prompt's version is stamped into outputs
(frontmatter / generated_by.prompt_version) for traceability.

Rules baked in everywhere:
- respond in the same language the user spoke
- return ONLY JSON when asked (Ollama format:"json" enforces validity)
- never invent data; use null for unknowns
"""

PROMPT_VERSIONS = {
    "dream_split": "1.0.0",
    "journal_enrich": "1.0.0",
    "intent_classify": "1.0.0",
    "note_draft": "1.0.0",
    "polish_note": "1.0.0",
    "query_answer": "1.0.0",
    "organize_plan": "1.0.0",
    "creative_assess": "1.0.0",
    "stats_v1": "1.0.0",
    "brief_me": "1.0.0",
    "fix_that": "1.0.0",
};

LANG_RULE = (
    "ALWAYS respond in the SAME LANGUAGE the user spoke — English, Portuguese, or Russian. "
    "NEVER translate: if the user wrote in Russian, every text you produce (headings, notes, "
    "tags aside) must be in Russian; if in Portuguese, in Portuguese; if in English, in English."
)


def polish_note(transcript: str) -> str:
    """Raw transcript -> clean, structured Obsidian note (JSON)."""
    return (
        "You clean up a RAW voice transcript into a well-formed Obsidian note.\n"
        "Rules:\n"
        "- Preserve the speaker's meaning EXACTLY — restructure, never invent or drop content.\n"
        "- Fix speech artifacts: filler words (um, uh, like), false starts, repetitions.\n"
        "- Structure with Markdown: a clear opening line, then bullet points for distinct\n"
        "  thoughts. Keep the speaker's reasoning order visible.\n"
        "- title: a short clean note title (not a sentence).\n"
        "- content: the formatted Markdown body (no H1 heading — the template adds it).\n"
        "- tags: 1-4 lowercase topical tags.\n"
        "\n" + LANG_RULE + "\n"
        'Return ONLY valid JSON: {"title": "...", "content": "...", "tags": ["..."]}\n'
        "\nRaw transcript:\n"
        '"""\n' + transcript + '\n"""\n'
    )


def dream_split(narration: str) -> str:
    return f"""You are a dream analysis parser. The user narrated one or more dreams.
Split the narration into INDIVIDUAL dreams. For each dream return:
- title: evocative 3-6 word title
- summary: 1-2 sentence description
- narration: the user's own words for this dream, lightly cleaned of speech artifacts (um, uh, false starts), meaning preserved
- themes: list of 2-6 symbolic themes (lowercase single words)
- emotional_tone: dominant emotion or mix
- vividness: 1-10 integer (how vivid the user's description suggests)
- lucidity: true/false (dreamer aware it was a dream?)

{LANG_RULE}
Return ONLY valid JSON: {{"dreams": [{{...}}, ...]}}
If there is exactly one dream, return a list with one element. If the text is not about a dream at all, return {{"dreams": []}}.

User narration:
\"\"\"{narration}\"\"\""""


def journal_enrich(entry_text: str) -> str:
    return f"""You tag a journal entry for a quantified-self pipeline.
The heading MUST be written in the same language as the entry text (never translate it).
Analyze this journal entry and return:
- heading: short 2-5 word label for the entry (like a section title)
- tags: list of lightweight structured stat tags extracted from the text, each formatted "category=value".
  Allowed categories: mood (0-10), energy (0-10), food:<desc>, sleep, exercise, social, caffeine, pain, focus.
  Only include tags actually supported by the text. Empty list if none.

{LANG_RULE}
Return ONLY valid JSON: {{"heading": "...", "tags": ["mood=8", ...]}}

Journal entry:
\"\"\"{entry_text}\"\"\""""


def intent_classify(text: str) -> str:
    return f"""Classify the user's voice command for a personal knowledge assistant.
Categories:
- create_note: the user wants a new note created/drafted
- query: the user asks a question about their knowledge/notes ("what do I know about...")
- organize: the user wants vault organization (moving, tagging, tidying)
- capture: anything else — save the words verbatim as a capture

{LANG_RULE}
Return ONLY valid JSON: {{"kind": "create_note|query|organize|capture", "reason": "one short line"}}

Command:
\"\"\"{text}\"\"\""""


def note_draft(text: str) -> str:
    return f"""Draft a well-structured Obsidian Markdown note from the user's spoken intent.
Return:
- title: clean note title (not the raw voice text)
- content: the note body in Markdown. Expand sensibly on what the user said — structure with
  headings/lists where useful — but DO NOT invent facts the user didn't state.
- tags: 1-4 lowercase tags

{LANG_RULE}
Return ONLY valid JSON: {{"title": "...", "content": "markdown...", "tags": ["..."]}}

User intent:
\"\"\"{text}\"\"\""""


def query_answer(question: str, notes_ctx: str) -> str:
    return f"""You answer questions over the user's personal knowledge vault (Obsidian notes).
Rules:
- Answer ONLY from the provided notes. If they don't contain the answer, say so plainly.
- Cite sources inline as [[Note Name]] wikilinks wherever you use a note.
- Be concise: 3-8 sentences or a short list.
{LANG_RULE}

Question: {question}

Notes:
\"\"\"{notes_ctx}\"\"\""""


def organize_plan(inbox_notes: str) -> str:
    return f"""You organize a personal knowledge vault. For each Inbox note below, propose actions:
- move: {"action": "move", "from": "<rel path>", "to": "<folder>/<new name>.md", "reason": "..."}
- tag:  {"action": "tag", "from": "<rel path>", "tags": ["tag1", ...], "reason": "..."}
- none: leave it alone if unsure.

Only propose moves into these folders: Inbox, Projects, Areas, Resources, Archive.
Be conservative — propose only what you're confident about.

{LANG_RULE}
Return ONLY valid JSON: {{"actions": [{{...}}, ...]}}

Inbox notes (path, then content, truncated):
\"\"\"{inbox_notes}\"\"\""""


def creative_assess(notes_ctx: str) -> str:
    return f"""Assess the user's creative output for the day — notes they produced.
For EACH note return:
- rel: the note's path exactly as given
- novelty, depth, clarity, actionability: 0-10 integers
- domain: one lowercase tag (programming, writing, design, research, personal, ...)
- format: one lowercase tag (note, essay, spec, todo, idea_capture, meeting_notes, moc, ...)
Do NOT assess connectivity — that is computed deterministically elsewhere.

{LANG_RULE}
Return ONLY valid JSON: {{"assessments": [{{...}}, ...]}} — one entry per note, same order.

Notes (path, then content, truncated):
\"\"\"{notes_ctx}\"\"\""""


def stats_v1(day: str, entries_ctx: str, creative_block: str, history_ctx: str,
             precomputed: str) -> str:
    return f"""You are a Quantified Self analysis engine. Analyze the user's entries from {day}
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
   {{"priority": int, "category": str, "action": str, "rationale": str, "confidence": 0-1}} —
   rationale must cite specific evidence from the entries.
7. Use the PRECOMPUTED numbers (correlations, trends, deltas) exactly as given when writing
   "insights.correlations" and trend text — do not invent or recompute statistics.
8. {LANG_RULE} — except JSON keys and category names, which stay in English.

Schema skeleton (fill all categories, estimates flagged with "_estimate": true where inferred):
{{
  "date": "{day}", "generated_at": "<now ISO>", "generated_by": {{"model": "<your model>", "prompt_version": "1.0.0"}},
  "metadata": {{"completeness_score": 0-100, "confidence": "low|medium|high"}},
  "creative_output": <use the provided creative block as the base, add your notes>,
  "sleep": {{...}}, "mood": {{...}}, "energy": {{...}}, "physical": {{...}},
  "nutrition": {{...}}, "cognitive": {{...}}, "social": {{...}}, "environment": {{...}},
  "habits": {{...}}, "time_use": {{...}},
  "derived": {{"readiness_score": int, "wellbeing_index": float, "trending": "...",
               "recommendations": [...], "radar_chart_data": {{"labels": [...], "values": [...], "unit": "0-100"}}}},
  "insights": {{"key_themes": [...], "emotional_summary": "...", "narrative": "...",
                "correlations": <use precomputed>, "anomalies": [...], "journal_quote": "..."}}
}}

TODAY'S ENTRIES:
\"\"\"{entries_ctx}\"\"\"

CREATIVE OUTPUT (precomputed assessment — use as-is for the creative_output block):
\"\"\"{creative_block}\"\"\"

HISTORY (last 7 days of stats, for trend context):
\"\"\"{history_ctx}\"\"\"

PRECOMPUTED NUMBERS (authoritative — do not alter):
\"\"\"{precomputed}\"\"\""""


def brief_me(stats_ctx: str, todos: int, streak: int) -> str:
    return f"""Generate a 60-second personal morning briefing from yesterday's stats.
Format as a short spoken script (3-5 sentences), friendly and honest.
Mention: sleep, mood/energy highlights, the single top recommendation, and open TODOs ({todos} open).
Capture streak: {todos and streak} days.

{LANG_RULE}
Return plain text (no markdown headings), max 90 words.

Stats:
\"\"\"{stats_ctx}\"\"\""""


def fix_that(last_action: str, amendment: str) -> str:
    return f"""The user issued a voice amendment to the last action performed by an assistant.

Last action: {last_action}
Amendment: "{amendment}"

Decide how to apply it. Return ONLY valid JSON:
{{"type": "retitle", "title": "..."}}  — rename the note/file
{{"type": "retag", "tags": ["..."]}}    — replace frontmatter tags
{{"type": "refile", "folder": "..."}}   — move to another managed folder (dream|journal|stats|inbox)
{{"type": "none"}}                      — no sensible way to apply

{LANG_RULE}"""
