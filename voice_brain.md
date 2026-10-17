# Voice Brain — Voice-Controlled Local Second Brain

## Executive Summary

A **fully local, voice-first knowledge assistant** that lives inside your Obsidian / Markdown vault. Activate it with a single shortcut on Omarchy, speak naturally, and let Whisper transcribe + Gemma 4 reason over your entire note collection. Create notes, ask questions, reorganize your knowledge graph, capture dreams, log your day, and auto-generate a quantified-self JSON for visualization — all without touching the keyboard or sending a byte to the cloud.

**Codename:** `voice-brain`  
**Runtime:** Python (backend) + Omarchy/Hyprland integration (frontend)  
**Stack:** Whisper (local STT) → Gemma 4 (local LLM) → Markdown filesystem (your vault)

---

## Why This Is Unique

| Existing Tool | Problem | How Voice Brain Solves It |
|-------------|---------|--------------------------|
| Obsidian Copilot | Cloud-dependent, monthly cost | 100% local, zero API keys |
| Apple Siri / Google Assistant | Can't reason over your notes | Deep context from your vault |
| Ollama web UI | Typing-heavy, no Obsidian integration | Voice-native, writes directly to vault |
| Standard RAG pipelines | Chunking kills context, complex setup | Gemma 4's 1M context = your *entire* vault in one shot for most users |
| Obsidian plugins (Auto Note Mover, etc.) | Dumb rule-based | LLM-powered semantic organization |
| Dream journal apps | Cloud-only, no integration with rest of life | Dreams feed into sleep stats and overall wellbeing picture |
| Quantified Self tools (Oura, Whoop) | Hardware-locked, exported data is messy | Derived from your own words, in a format you control |

**The killer insight:** Most personal knowledge bases are <500K tokens. Gemma 4's 1M context window means you don't need vector DBs, embeddings, or chunking. You can literally pass your *entire vault* as context and ask it to reason across everything. This eliminates 90% of the infra complexity that kills weekend projects.

**The second insight:** Your voice captures *subjective experience* better than any wearable. By combining dream recall, daily journal entries, and mood/energy/food logging into a daily quantified-self JSON, you build a dataset that no wearable can match — fully owned, fully private, fully extensible.

---

## Vault Structure (Auto-Created)

Voice Brain manages **four special folders** in your Obsidian vault. If they don't exist, they are created on first run:

```
~/Documents/Obsidian/Omarchy-Yev/           # Your vault root
├── Dream Journal/                          # One file per dream
│   ├── 2025-01-15_Flying_Over_the_City.md
│   ├── 2025-01-15_Old_School_Reunion.md
│   └── 2025-01-16_Submerged_in_Crystal.md
│
├── Journal/                                # One file per day
│   ├── 2025-01-15.md                       # All "log this" entries for the day
│   ├── 2025-01-16.md
│   └── 2025-01-17.md
│
├── Stats/                                  # One JSON per day
│   ├── 2025-01-15.json                     # Auto-generated at end of day
│   ├── 2025-01-16.json
│   └── 2025-01-17.json
│
└── (Your existing folders: Inbox, Projects, Areas, Resources, Archive, Daily)
```

**Auto-creation logic:** On daemon startup, Voice Brain checks for these four folders. Missing folders are created with a `.voice-brain-generated` marker file explaining their purpose.

---

## Core Interaction Model

### Push-to-Talk (Primary)

```
[Press SUPER + ALT + V]     →  Audio indicator appears (Omarchy OSD/notification)
[Speak command]             →  Real-time waveform visualizer
[Release SUPER + ALT + V]   →  Processing indicator → Result
```

### Voice-Activated Mode (Future)

```
[Press SUPER + ALT + V]     →  System enters "listening mode"
"Hey brain, create a note..."  →  Detects wake phrase, processes command
"Thank you" / 5s silence    →  Exits listening mode
```

### Audio Feedback States

| State | Visual | Audio (optional) |
|-------|--------|-----------------|
| Ready | Subtle pulse on bar widget | Soft chime |
| Recording | Expanding waveform ring | None |
| Processing | Spinning indicator | Gentle hum |
| Success | Green check flash | Success chime |
| Error | Red pulse | Error tone |
| Dream detected | Purple glow | Star chime |
| Stats generated | Blue chart icon | Data chime |

---

## Phrase-Triggered Note Types

Voice Brain uses **phrase prefixes** to route your voice to the right vault destination. Everything else falls through to the general command handler (create note, ask question, etc.)

### Trigger Hierarchy

```
Transcription received
        │
        ├──▶ "I had a dream..." ──────▶ Dream Journal (CREATE multiple notes)
        │
        ├──▶ "log this" ──────────────▶ Daily Journal (APPEND to today's note)
        │
        ├──▶ "log stat" / "track" ────▶ Explicit stat logging (feeds Stats JSON)
        │
        ├──▶ "generate stats" ────────▶ Stats JSON auto-generation trigger
        │
        └──▶ (no match) ──────────────▶ General command (create note, query, organize)
```

> **Priority rule:** If you say "log this: I had a dream about flying", the "I had a dream" prefix takes priority and routes to Dream Journal. The "log this" prefix only activates when it's the *first phrase* of the transcription.

---

## 1. DREAM JOURNAL

### Trigger Phrase
- **"I had a dream..."** (primary)
- **"I dreamed about..."**
- **"In my dream..."**
- **"Last night I dreamt..."**
- **"There was this dream..."**

### Behavior

When Voice Brain detects a dream trigger, it:

1. **Captures the full audio transcription**
2. **Passes to Gemma 4 with a splitting prompt:**
3. **Receives structured JSON back**
4. **Creates one Markdown file per dream**

### Dream Splitting Logic

You might narrate multiple dreams in one audio session:

> *"I had a dream where I was flying over a neon-lit city... then I had another dream where I was back in high school but all my classmates were cats... and then there was this weird fragment where I was trying to eat soup with a fork."*

Gemma 4 is prompted to split this into:
- Dream 1: Flying over neon city
- Dream 2: High school with cat classmates
- Dream 3: Fragment — eating soup with fork

**Prompt sent to Gemma:**

```
You are a dream analysis parser. The user narrated the following dreams.
Split them into INDIVIDUAL dreams. For each dream, return:
- title: evocative 3-6 word title (e.g. "Flying Over the Neon City")
- summary: 1-2 sentence description
- themes: [list of symbolic themes]
- emotional_tone: [dominant emotion or mixed]
- vividness_score: 1-10
- lucidity: true/false (was the dreamer aware it was a dream?)
- timestamp: ISO datetime (use the recording timestamp as base)

Return ONLY valid JSON in this format:
{"dreams": [{...}, {...}]}

User narration:
"{transcription}"
```

### Dream Journal Note Format

Each dream becomes a file: `Dream Journal/YYYY-MM-DD_{Title_Snake_Case}.md`

```markdown
---
dream_id: "2025-01-15_001"
dreamt_at: "2025-01-15T07:30:00"
recorded_at: "2025-01-15T08:15:00"
title: "Flying Over the Neon City"
vividness: 8
lucidity: false
themes:
  - flying
  - cities
  - technology
  - freedom
emotional_tone: "exhilarated, slightly anxious"
tags:
  - dream
  - flying
  - vivid
created_by: voice-brain
model: gemma3:9b
---

# Flying Over the Neon City

**Dreamt:** 2025-01-15 ~07:30  
**Recorded:** 2025-01-15 08:15  
**Vividness:** 8/10 | **Lucid:** No

## Narration

I was flying over a neon-lit city, skimming between skyscrapers. The lights were all purple and teal. I felt completely free but also worried I'd crash into a building. I could feel the wind on my face. It was incredibly vivid.

## Themes & Symbols

- **Flying**: desire for freedom, escape from constraints
- **Neon city**: modern anxiety, overstimulation
- **Purple/teal lights**: creativity, intuition

## Emotional Arc

Started exhilarated → mild anxiety near the end → woke up with adrenaline.

## Connections

- Similar to dream on 2025-01-05 (flying theme recurring)
- City imagery links to current work stress on downtown project

---

*Auto-generated by Voice Brain*  
*Edit freely — this is your journal.*
```

### Multi-Dream Example

One audio session → three files created:

```
Dream Journal/
├── 2025-01-15_Flying_Over_the_Neon_City.md
├── 2025-01-15_High_School_Cat_Classmates.md
└── 2025-01-15_Fragment_Soup_with_a_Fork.md
```

All three get cross-linked in their "Connections" sections.

### Dream Re-entry Mode

If you wake from a dream and want to capture it *before* you forget:

```
[Press SUPER + ALT + V]
"I had a dream" (pause — fall back asleep)
[Release] — auto-saved, processed later
```

Voice Brain buffers the audio and processes it when you explicitly confirm (or auto-processes if configured).

---

## 2. DAILY JOURNAL

### Trigger Phrase
- **"log this"** (must be first words)
- **"log that"**
- **"journal this"**
- **"remember this"**

### Behavior

```
[Press SUPER + ALT + V]
"log this: just finished a great workout, feel energized"
[Release]
```

→ Appends to `Journal/2025-01-15.md`

### Daily Journal Note Format

One file per day. Entries append with timestamps.

```markdown
---
date: "2025-01-15"
created_by: voice-brain
entry_count: 5
---

# Journal — Wednesday, January 15, 2025

## 08:15 — Morning Energy

log this: just finished a great workout, feel energized. Had eggs and avocado for breakfast. Slept okay but woke up twice.

---

## 12:30 — Lunch Reflection

log this: team lunch was fun, Sarah mentioned the Q3 roadmap looks aggressive. I think we can hit it if we prioritize the API refactor. Feeling optimistic but need to focus.

---

## 15:45 — Afternoon Dip

log this: hit a wall around 3pm. Too much coffee this morning? Had a second espresso at 11. Need to cut back. Mood dropped from 8 to 5. Took a 10min walk, feeling better now.

---

## 19:20 — Evening Wind-Down

log this: made a really good stir-fry for dinner. Lots of vegetables, some tofu, brown rice. Feeling nourished. Planning to read before bed instead of screens.

---

## 22:00 — Day Closing

log this: solid day overall. Productive morning, social lunch, managed the afternoon dip well. Sleep hygiene goal: no screens after 21:30 tomorrow.

---

*Voice Brain — {entry_count} entries on {date}*
```

### Key Behaviors

| Scenario | Action |
|----------|--------|
| First "log this" of the day | Creates `Journal/2025-01-15.md` with frontmatter |
| Subsequent "log this" same day | Appends with `---` separator + timestamp |
| "log this" on a new day | Creates new daily file |
| Entry contains multiple thoughts | Preserved as-is — Gemma 4 splits into themes during stats generation |
| Entry is very long | Allowed — no truncation. Stats generator will summarize. |
| Entry contains conflicting info | Preserved. Stats generator handles contradictions with confidence scores. |

### Implicit Stat Capture

Voice Brain itself extracts keywords from journal entries to help the daily stats generation:

- Mentions of food → nutrition tracking
- Mentions of sleep quality → sleep tracking  
- Mood words ("energized", "anxious", "happy") → mood tracking
- Exercise mentions → physical activity tracking
- Social interactions → social tracking
- Energy levels → vitality tracking

These extractions are stored as lightweight metadata tags on the journal entry, invisible to you but used by the stats generator.

---

## 3. CREATIVE OUTPUT TRACKING

This is one of Voice Brain's most unique features. While `Dream Journal`, `Journal`, and `Stats` track your *inputs* (what happened to you), **Creative Output Tracking** measures your *outputs* (what you created).

### What Counts as Creative Output

Any Markdown file created today **outside** the three special folders:

| Folder Type | Examples | Counts? |
|-------------|----------|---------|
| `Inbox/` | Quick capture, later processed | ✅ Yes (until moved) |
| `Projects/` | Project specs, meeting notes, TODOs, code documentation | ✅ Yes |
| `Resources/` | Book summaries, learning notes, reference material | ✅ Yes |
| `Areas/` | Long-term responsibility notes (health, finances, relationships) | ✅ Yes |
| `Archive/` | Completed projects, old references | ✅ Yes |
| `Daily/` | Daily notes (if separate from Journal) | ✅ Yes |
| `Dream Journal/` | Dream captures | ❌ No — input/consumption |
| `Journal/` | Daily logs | ❌ No — input/consumption |
| `Stats/` | System-generated JSONs | ❌ No — system output |

### Creativity Assessment Dimensions

Gemma 4 analyzes each qualifying note and scores:

| Dimension | Scale | What It Measures |
|-----------|-------|-----------------|
| `novelty` | 0-10 | How original is the idea? New concept vs. rehash |
| `depth` | 0-10 | How deeply does it explore the topic? Surface vs. profound |
| `connectivity` | 0-10 | How many links to other notes? Isolated vs. networked |
| `clarity` | 0-10 | How well-written and structured? Confused vs. lucid |
| `actionability` | 0-10 | Does it lead to something? Philosophical vs. practical |
| `domain` | tag | Programming, Writing, Design, Research, Personal, etc. |
| `format` | tag | Note, Essay, Spec, TODO list, Sketch, MOC, etc. |

### Daily Creative Output Block (in Stats JSON)

See the full schema in the Stats section. Key fields:

```json
"creative_output": {
  "notes_created_count": 4,
  "notes_created_today": [
    "Projects/Landing_Page_API_Spec.md",
    "Resources/Rust_Async_Patterns.md",
    "Inbox/Random_Idea_Voice_Controller.md",
    "Projects/Meeting_Sarah_Roadmap.md"
  ],
  "total_words_produced": 1450,
  "domains": ["programming", "project_management", "ideas"],
  "formats": ["spec", "learning_note", "idea_capture", "meeting_notes"],
  "novelty_average": 7,
  "depth_average": 6,
  "connectivity_average": 5,
  "clarity_average": 8,
  "actionability_average": 7,
  "creativity_score": 66,
  "creativity_score_unit": "0-100",
  "creative_hours_estimate": 3,
  "peak_creative_time": "09:00-11:00",
  "creative_mode": "deep_work",
  "source": "Vault filesystem scan",
  "notes": "Strong morning creative block. Two deep technical notes and one project spec. Connectivity score lower than usual — notes are isolated, consider linking them."
}
```

### The Creative Velocity Dashboard Concept

Over time, this data answers:
- "Am I producing more or less than last month?"
- "What time of day do I do my best creative work?"
- "Does exercise boost my creative output?" (correlate with physical)
- "Do I write better after good sleep?" (correlate with sleep)
- "What's my creative/domain distribution?" (too much code, not enough writing?)
- "Are my notes getting more connected over time?" (graph health)

### Tracking Method

Voice Brain scans your vault at stats-generation time:

1. Find all `.md` files modified today
2. Exclude files in `Dream Journal/`, `Journal/`, `Stats/`
3. For each qualifying note, read content + frontmatter
4. Pass to Gemma 4 with creativity assessment prompt
5. Aggregate into daily creative output block
6. Include in overall Stats JSON

**Prompt excerpt for Gemma 4:**

```
Analyze the following notes created today. These represent the user's CREATIVE OUTPUT — things they produced, not just consumed or logged.

For each note, assess:
- novelty: 0-10 (how original)
- depth: 0-10 (how thorough)
- connectivity: 0-10 (how linked to other notes)
- clarity: 0-10 (how well written)
- actionability: 0-10 (does it lead to action)
- domain: primary topic area
- format: type of note

Then provide a daily summary:
- total_notes
- total_words
- averages per dimension
- overall creativity_score (0-100)
- peak creative time (inferred from file mtimes if available)
- creative_mode: "deep_work" | "scattered" | "reflective" | "planning"
- notes: 2-3 sentences of insight

Notes:
{note contents with paths}
```

---

## 4. STATS / QUANTIFIED SELF JSON

### Trigger Phrase
- **"generate stats"** — generates today's stats from today's entries
- **"generate stats for yesterday"** — retroactive generation
- **"how was my day?"** — generates + reads summary aloud (future TTS)
- **"analyze my week"** — aggregates last 7 days into a trend report

### Behavior

```
[Press SUPER + ALT + V]
"generate stats"
[Release]
```

Voice Brain:
1. Collects all of today's entries:
   - `Dream Journal/2025-01-15_*.md`
   - `Journal/2025-01-15.md`
2. Passes them to Gemma 4 with a structured extraction prompt
3. Receives JSON conforming to the Voice Brain Stats Schema
4. Saves to `Stats/2025-01-15.json`
5. (Optional) Generates a human-readable `Stats/2025-01-15.md` summary

### Deep Research: Best JSON Format for Quantified Self

After analyzing Open mHealth, Apple HealthKit, WHOOP, Oura Ring, Fitbit, Garmin, and biohacker communities (Quantified Self Forum, r/Biohackers, r/QuantifiedSelf), here is the optimal format:

**Design Principles:**
1. **Time-series native** — Easy to query `$.sleep.quality_score` across 365 files for a chart
2. **Normalized scores** — All subjective ratings on 0-10 or 0-100 for consistent visualization
3. **Source-attributed** — Every metric links to the entry that generated it (traceability)
4. **Extensible** — Add new metric categories without breaking existing consumers
5. **AI-optimal** — Structured enough for consistent generation, flexible enough for nuance
6. **App-ready** — Flat paths for simple charting (`sleep.quality_score`, `mood.average`), rich objects for detail views
7. **Human-debuggable** — Both machine-readable AND includes human-readable summaries

**Why not Open mHealth / FHIR / Apple HealthKit directly?**
- Open mHealth is XML-first, verbose, and abandoned (last update 2016)
- FHIR is clinical-overhead hell — hundreds of fields you'll never use
- Apple HealthKit export is XML, proprietary, and hard to merge with subjective data
- **Oura / WHOOP APIs** are the best reference for modern consumer biohacking — their daily readiness/sleep/activity model is exactly what we want
- **Conclusion:** Design a custom JSON that *draws from* Oura's simplicity, adds subjective depth from journaling, and includes LLM-generated insights

---

### Voice Brain Stats Schema v1.0.0

```json
{
  "$schema": "voice-brain://stats-schema/v1.0.0",
  "date": "2025-01-15",
  "generated_at": "2025-01-15T23:59:00Z",
  "generated_by": {
    "model": "gemma3:9b",
    "quantization": "Q4_K_M",
    "temperature": 0.3,
    "prompt_version": "1.0.0"
  },

  "metadata": {
    "schema_version": "1.0.0",
    "source_entries": {
      "dreams": [
        "Dream Journal/2025-01-15_Flying_Over_the_Neon_City.md",
        "Dream Journal/2025-01-15_High_School_Cat_Classmates.md"
      ],
      "journal_entries": [
        "Journal/2025-01-15.md#0815",
        "Journal/2025-01-15.md#1230",
        "Journal/2025-01-15.md#1545",
        "Journal/2025-01-15.md#1920",
        "Journal/2025-01-15.md#2200"
      ],
      "explicit_stats": []
    },
    "completeness_score": 85,
    "confidence": "high"
  },

  "creative_output": {
    "notes_created_count": 4,
    "notes_created_today": [
      "Projects/Landing_Page_API_Spec.md",
      "Resources/Rust_Async_Patterns.md",
      "Inbox/Random_Idea_Voice_Controller.md",
      "Projects/Meeting_Sarah_Roadmap.md"
    ],
    "total_words_produced": 1450,
    "domains": ["programming", "project_management", "ideas"],
    "formats": ["spec", "learning_note", "idea_capture", "meeting_notes"],
    "novelty_average": 7,
    "novelty_average_scale": "0-10",
    "depth_average": 6,
    "depth_average_scale": "0-10",
    "connectivity_average": 5,
    "connectivity_average_scale": "0-10",
    "clarity_average": 8,
    "clarity_average_scale": "0-10",
    "actionability_average": 7,
    "actionability_average_scale": "0-10",
    "creativity_score": 66,
    "creativity_score_unit": "0-100",
    "creative_hours_estimate": 3,
    "peak_creative_time": "09:00-11:00",
    "creative_mode": "deep_work",
    "creative_mode_options": ["deep_work", "scattered", "reflective", "planning", "minimal"],
    "source": "Vault filesystem scan + Gemma 4 analysis",
    "notes": "Strong morning creative block. Two deep technical notes and one project spec. Connectivity score lower than usual — notes are isolated, consider linking them."
  },

  "sleep": {
    "quality_score": 72,
    "quality_score_unit": "0-100",
    "duration_hours": 7.5,
    "duration_hours_estimate": true,
    "efficiency_percent": 88,
    "subjective_rating": 7,
    "subjective_rating_scale": "0-10",
    "sleep_onset_minutes": 20,
    "waking_count": 2,
    "deep_sleep_estimate_hours": 1.5,
    "rem_sleep_estimate_hours": 2.0,
    "dream_recall": true,
    "dream_count": 2,
    "dream_vividness_average": 7.5,
    "lucid_dreams_count": 0,
    "sleep_aid_used": null,
    "bedtime_estimate": "23:30",
    "wake_time_estimate": "07:00",
    "source": "Dream Journal + Journal/2025-01-15.md#0815",
    "notes": "Woke twice (around 3am and 6am). Dreams were vivid and emotionally complex. Fell asleep within 20 minutes. Overall decent night but not fully restorative."
  },

  "mood": {
    "average_score": 6.5,
    "average_score_scale": "0-10",
    "morning": 7,
    "afternoon": 5,
    "evening": 7,
    "night": null,
    "dominant_emotion": "content",
    "emotional_variability": "moderate",
    "emotional_arc": "energized → dip → recovery → stable",
    "anxiety_level": 3,
    "anxiety_level_scale": "0-10",
    "depression_screen": 2,
    "depression_screen_scale": "0-10",
    "source": "Journal/2025-01-15.md",
    "notes": "Strong start, midday dip likely caffeine-related, recovered well with walk and good dinner."
  },

  "energy": {
    "average_score": 70,
    "average_score_scale": "0-100",
    "morning": 85,
    "afternoon": 45,
    "evening": 65,
    "fatigue_level": 4,
    "fatigue_level_scale": "0-10",
    "caffeine_response": "negative_afternoon_crash",
    "source": "Journal/2025-01-15.md#0815,1545",
    "notes": "Post-workout energy was excellent. Second espresso caused noticeable crash."
  },

  "physical": {
    "exercise": {
      "did_exercise": true,
      "type": "strength_training",
      "duration_minutes": 45,
      "intensity": "moderate",
      "perceived_exertion": 7,
      "perceived_exertion_scale": "0-10"
    },
    "steps_estimate": 8500,
    "active_hours_estimate": 2,
    "sedentary_hours_estimate": 10,
    "pain_points": [
      {
        "location": "lower_back",
        "severity": 2,
        "severity_scale": "0-10",
        "quality": "tension",
        "notes": "Mild tightness, not debilitating"
      }
    ],
    "subjective_recovery": 7,
    "subjective_recovery_scale": "0-10",
    "body_composition_notes": null,
    "source": "Journal/2025-01-15.md#0815",
    "notes": "Good workout. Lower back tension noted — likely form issue on deadlifts."
  },

  "nutrition": {
    "meals": [
      {
        "time": "08:00",
        "type": "breakfast",
        "description": "eggs and avocado",
        "quality_estimate": 8,
        "macros_guess": { "protein": "high", "fat": "high", "carbs": "low" }
      },
      {
        "time": "12:30",
        "type": "lunch",
        "description": "team lunch",
        "quality_estimate": 6,
        "macros_guess": null
      },
      {
        "time": "19:20",
        "type": "dinner",
        "description": "stir-fry with tofu, vegetables, brown rice",
        "quality_estimate": 9,
        "macros_guess": { "protein": "moderate", "fat": "moderate", "carbs": "moderate", "fiber": "high" }
      }
    ],
    "snacks_count": 0,
    "hydration_liters_estimate": 2.0,
    "caffeine_mg_estimate": 200,
    "alcohol_units": 0,
    "sugar_intake_estimate": "low",
    "dietary_quality_score": 78,
    "dietary_quality_score_unit": "0-100",
    "fasting_hours": 14,
    "source": "Journal/2025-01-15.md",
    "notes": "Two solid meals, one social lunch (quality unknown). Good hydration. High caffeine."
  },

  "cognitive": {
    "focus_score": 80,
    "focus_score_unit": "0-100",
    "flow_states_count": 2,
    "productivity_score": 75,
    "creativity_score": 7,
    "creativity_score_scale": "0-10",
    "mental_clarity": 7,
    "mental_clarity_scale": "0-10",
    "learning_activity": "none_logged",
    "reading_minutes": 0,
    "source": "Journal/2025-01-15.md",
    "notes": "Deep work session implied by productive morning. Planning to read tonight (not yet executed at time of stats generation)."
  },

  "social": {
    "interactions_count": 4,
    "interactions_quality_average": 7,
    "interactions_quality_scale": "0-10",
    "primary_social_context": "work",
    "loneliness_score": 2,
    "loneliness_score_scale": "0-10",
    "conflict_notes": null,
    "source": "Journal/2025-01-15.md#1230",
    "notes": "Team lunch was energizing. Good conversation with Sarah about roadmap."
  },

  "environment": {
    "weather_perceived": "sunny_cold",
    "temperature_c_estimate": 5,
    "sunlight_hours_estimate": 3,
    "screen_time_hours_estimate": 8,
    "nature_exposure_minutes": 10,
    "work_environment": "office",
    "commute_minutes": 30,
    "source": "Journal/2025-01-15.md (inferred)",
    "notes": "Morning walk provided some sunlight. Screen time high in afternoon."
  },

  "habits": {
    "meditation_minutes": 0,
    "cold_exposure": false,
    "breathwork": false,
    "supplements_taken": [],
    "sleep_hygiene_score": 6,
    "sleep_hygiene_scale": "0-10",
    "source": "Journal/2025-01-15.md",
    "notes": "Planned reading before bed (sleep hygiene +). Second espresso late (sleep hygiene -)."
  },

  "time_use": {
    "deep_work_hours_estimate": 4,
    "meetings_hours_estimate": 1,
    "creative_hours_estimate": 2,
    "social_hours_estimate": 1.5,
    "chores_hours_estimate": 0.5,
    "leisure_hours_estimate": 2,
    "sleep_hours": 7.5,
    "source": "Journal/2025-01-15.md (inferred)",
    "notes": "Good deep work block. Balanced day overall."
  },

  "derived": {
    "readiness_score": 74,
    "readiness_score_unit": "0-100",
    "wellbeing_index": 7.1,
    "wellbeing_index_scale": "0-10",
    "consistency_score": 78,
    "trending": "stable_slight_decline",
    "trend_explanation": "Compared to yesterday: sleep quality down 8pts (waking events), mood variability up, but nutrition and exercise strong.",
    "day_type": "productive_with_dip",
    "archetype": "The Recovering Optimizer",

    "scores_breakdown": {
      "sleep": 72,
      "mood": 65,
      "energy": 70,
      "physical": 75,
      "nutrition": 78,
      "cognitive": 80,
      "creative_output": 66,
      "social": 70,
      "environment": 55,
      "habits": 60,
      "time_use": 75
    },

    "radar_chart_data": {
      "labels": ["Sleep", "Mood", "Energy", "Physical", "Nutrition", "Cognitive", "Creative Output", "Social", "Environment", "Habits", "Time Use"],
      "values": [72, 65, 70, 75, 78, 80, 66, 70, 55, 60, 75],
      "unit": "0-100"
    },

    "recommendations": [
      {
        "priority": 1,
        "category": "sleep",
        "action": "Cut caffeine after 11am",
        "rationale": "Two waking events and afternoon crash correlate with 200mg caffeine intake. Second espresso at 11am likely contributed.",
        "confidence": 0.85
      },
      {
        "priority": 2,
        "category": "physical",
        "action": "Add lower back stretching before bed",
        "rationale": "Mild lower back tension noted two days this week. Pre-sleep stretching may prevent escalation.",
        "confidence": 0.75
      },
      {
        "priority": 3,
        "category": "creative_output",
        "action": "Link today's isolated notes into your knowledge graph",
        "rationale": "Connectivity score is 5/10 — strong depth and clarity but low cross-linking. Adding [[WikiLinks]] would boost graph health and serendipity.",
        "confidence": 0.80
      },
      {
        "priority": 4,
        "category": "energy",
        "action": "Schedule a 15-min walk at 3pm",
        "rationale": "Afternoon energy dip is consistent. Walking break today helped recovery.",
        "confidence": 0.80
      }
    ],

    "warnings": [
      {
        "severity": "moderate",
        "category": "caffeine",
        "message": "Caffeine intake trending upward (200mg today, 150mg yesterday)",
        "trend_days": 2
      }
    ]
  },

  "insights": {
    "key_themes": ["productivity", "recovery", "social_connection", "caffeine_sensitivity"],
    "emotional_summary": "Day started strong with exercise and good food. Social lunch boosted mood. Caffeine overconsumption caused a predictable dip. Evening recovery was solid. Overall an above-average day with one clear optimization point.",
    "narrative": "The Recovering Optimizer had a productive morning powered by exercise and intention, hit a midday wall from self-inflicted caffeine overload, but recovered gracefully with a walk and a nourishing dinner. Sleep was decent but fragmented. The pattern is clear: mornings are a strength, afternoons need structural support.",
    "correlations": [
      {
        "factor_a": "sleep_quality_score",
        "factor_b": "creative_output.creativity_score",
        "relationship": "positive",
        "strength": 0.61,
        "n_day_support": 7,
        "notes": "Days with sleep quality >75 show 20-30% higher creative output scores"
      },
      {
        "factor_a": "caffeine_mg_estimate",
        "factor_b": "afternoon_energy",
        "relationship": "negative",
        "strength": 0.72,
        "n_day_support": 3,
        "notes": "200mg+ caffeine days show 15-20pt afternoon energy drops"
      },
      {
        "factor_a": "exercise",
        "factor_b": "morning_mood",
        "relationship": "positive",
        "strength": 0.68,
        "n_day_support": 5,
        "notes": "Workout days correlate with morning mood scores 7+"
      },
      {
        "factor_a": "social_interaction_quality",
        "factor_b": "evening_mood",
        "relationship": "positive",
        "strength": 0.55,
        "n_day_support": 2,
        "notes": "Emerging pattern — needs more data"
      }
    ],
    "anomalies": [
      "Higher than average dream recall (2 vivid dreams)",
      "Afternoon energy dip steeper than typical (45pts)"
    ],
    "journal_quote": "Felt unstoppable after the workout",
    "dream_insights": "Flying dreams often appear during periods of creative confidence. The high school/cat dream may reflect social anxiety disguised as absurdity. Both dreams suggest the subconscious is processing professional and social themes simultaneously."
  }
}
```

### Schema Design Rationale

**1. Hierarchical + Flat Hybrid**
- Nested objects organize by domain (sleep, mood, physical)
- Flat derived scores enable simple charting: `data.map(d => d.derived.readiness_score)`

**2. Normalized Scores Everywhere**
- `0-10` for subjective ratings (human-intuitive)
- `0-100` for computed scores (app-friendly, color-gradient friendly)
- Explicit `_scale` fields document the range for future-proofing

**3. Source Attribution**
- Every category has a `source` string linking to files/entries
- `metadata.source_entries` provides full provenance
- Enables debugging: "Why did it score sleep at 72?" → Check source

**4. Estimate Flags**
- `duration_hours_estimate: true` signals this isn't measured data
- Distinguishes inferred-from-journal vs. explicit tracking (future wearables)
- Critical for data scientists consuming this JSON

**5. Time-Series Arrays Inside Categories**
- `nutrition.meals[]` with timestamps
- Enables meal-timing analysis, not just daily aggregates
- Future: `mood.hourly_readings[]` if you log multiple times

**6. Derived / Insights Separation**
- `derived` = computed metrics, scores, recommendations (machine-usable)
- `insights` = narrativity, correlations, anomalies, quotes (human-readable)
- Apps can show `derived` in dashboards and `insights.narrative` as a daily story

**7. Correlation Tracking**
- Not just daily data — tracks multi-day pattern discovery
- `n_day_support` tells you how strong the evidence is
- Over weeks, this becomes your personal "what affects what" map

**8. Radar Chart Ready**
- `radar_chart_data` is pre-computed for direct feeding into Chart.js/D3/Victory
- 11 dimensions = comprehensive but not overwhelming
- **Creative Output** is treated as a first-class dimension alongside Sleep and Mood

**9. Creative Velocity as a Leading Indicator**
- Most QS tools track *inputs* (sleep, food, steps). Voice Brain tracks *outputs* (notes produced, ideas captured, depth of thinking)
- Creative output is often a **leading indicator** of wellbeing — you create more when you're thriving
- The creativity score correlates with mood, energy, and sleep over multi-day windows
- Low creative output with high energy might indicate "productive but not fulfilling" work
- High creative output with low sleep might indicate manic/productivity-at-cost pattern

**10. Versioning**
- Structured recommendations with priority, confidence, rationale
- Can be surfaced as push notifications, daily briefings, or in-app cards
- Rationale includes the evidence — builds trust

**10. Versioning**
- `$schema`, `schema_version`, `generated_by.prompt_version` all versioned
- When the schema evolves, old JSON files remain valid and parseable

### Optional: Human-Readable Markdown Summary

For every `.json` file, an optional `.md` companion can be generated:

```markdown
# Daily Stats — January 15, 2025

**Readiness Score:** 74/100 | **Wellbeing Index:** 7.1/10

## Sleep
Quality: 72/100 | Duration: 7.5h | Dreams: 2 (vivid)

## Mood
Average: 6.5/10 | Arc: energized → dip → recovery → stable

## Energy
Average: 70/100 | Crash detected at 15:45 (caffeine-related)

## Physical
Workout: 45min strength | Steps: ~8,500 | Pain: mild lower back tension

## Nutrition
Quality: 78/100 | Meals: 3 | Caffeine: 200mg ⚠️

## Creative Output
Quality: 66/100 | Notes: 4 (1,450 words) | Domains: programming, project-mgmt, ideas | Peak: 09:00-11:00

## Top Recommendations
1. **Cut caffeine after 11am** (confidence: 85%)
2. **Link today's isolated notes** (confidence: 80%) — Connectivity score is low
   Your afternoon crash correlates with 200mg+ intake days.

## Today's Archetype
**The Recovering Optimizer** — productive morning, self-inflicted dip, graceful recovery.
```

### Stats Generation Prompt (for Gemma 4)

```
You are a Quantified Self analysis engine. Analyze the user's journal entries 
from today and produce a JSON document conforming to the Voice Brain Stats Schema.

Today's entries are provided below. Extract all metrics, infer what you can, 
and be honest about uncertainty (use estimate flags and confidence scores).

RULES:
1. Return ONLY valid JSON. No markdown, no explanations outside JSON.
2. All scores must be integers (no "N/A" — use null instead).
3. Every category MUST have a "notes" field with 1-3 sentences.
4. Recommendations must reference specific evidence from the entries.
5. Correlations should only be reported if you see them in today's data + history.
6. The "narrative" field should be a 2-3 sentence human story of the day.
7. If information is missing, omit the field or set to null — never hallucinate.

ENTRIES:
{ today's dream journal files }
{ today's journal file }
{ today's creative output notes (files modified today outside special folders) }

HISTORY (last 7 days for trend context):
{ last 7 stats JSON files }

OUTPUT: Valid JSON only.
```

### Scheduled Auto-Generation

```bash
# Cron job — generate stats at 11:59 PM daily
59 23 * * * /usr/bin/voice-brain --generate-stats --date today

# Or use Omarchy hook
omarchy hook install post-boot ~/.config/omarchy/hooks/post-boot.d/98-voice-brain-cron.sh
```

Cron script content:
```bash
#!/bin/bash
# Add to crontab via: crontab -e
export VAULT_PATH="$HOME/Documents/Obsidian/Omarchy-Yev"
export GEMMA_MODEL="gemma3:9b"
/usr/bin/voice-brain --generate-stats --date today --vault "$VAULT_PATH"
```

---

## General Command Categories

Everything that doesn't start with a journal trigger phrase goes here:

### 4. NOTE CREATION

| Voice Command | Action | Output |
|--------------|--------|--------|
| "Create a new note on Rust error handling" | Generates titled note with structured content | `Resources/Rust_Error_Handling.md` |
| "Start a project note for the landing page redesign" | Creates project scaffold with TODOs, links | `Projects/Landing_Page_Redesign.md` |
| "Add to my cooking note: sous vide steak at 54 degrees for 2 hours" | Appends to existing note or creates | `Resources/Cooking.md` |
| "Draft a blog post about local LLMs" | Full blog post in writing folder | `Projects/Blog_Local_LLMs.md` |
| "Create a MOC for machine learning" | Map of Content — index note with links to all ML notes | `Resources/MOC_Machine_Learning.md` |
| "Note from clipboard" | Creates note from clipboard content | `Inbox/From_Clipboard_2025-01-15.md` |

### 5. KNOWLEDGE QUERY

| Voice Command | Action |
|--------------|--------|
| "What do I know about async Rust?" | Searches vault, synthesizes answer with citations |
| "Summarize my notes on the landing page project" | Reads all project-linked notes, gives status |
| "When did I last talk to Sarah about the roadmap?" | Finds mentions across Daily notes |
| "What was that book recommendation about habits?" | Fuzzy search across all notes |
| "Compare my notes on Rust and Go concurrency" | Side-by-side synthesis with differences |
| "What are my open TODOs?" | Aggregates unchecked checkboxes across vault |
| "Find the note where I wrote about the 4-hour work week" | Semantic + keyword retrieval |

### 6. VAULT ORGANIZATION

| Voice Command | Action |
|--------------|--------|
| "Organize my notes by topic into folders" | Reads all Inbox notes, suggests moves, applies |
| "Tag all my programming notes with the right hashtags" | Adds Obsidian tags based on content |
| "Create a map of content for my project notes" | Generates MOCs for each project area |
| "Archive notes I haven't touched in 6 months" | Moves to Archive/ with date stamp |
| "Find duplicates and merge them" | Detects similar notes, proposes merges |
| "Populate my graph — add tags to orphan notes" | Finds notes with no links/tags, adds connections |

### 7. CREATIVE / ADVANCED

| Voice Command | Action |
|--------------|--------|
| "Write a weekly review from my daily notes" | Aggregates last 7 days into a synthesis |
| "What patterns do you see in my journal entries?" | Emotional/behavioral analytics on your own writing |
| "Create flashcards from my Rust notes" | Generates Anki-compatible Q&A pairs |
| "Suggest a reading list based on my gaps" | Analyzes what you know, suggests what to learn next |
| "What's contradicted in my notes?" | Finds conflicting information across your vault |
| "Generate a Zettelkasten ID for this note" | Creates unique timestamp ID, updates links |
| "Write a newsletter from my week's learnings" | Compiles interesting captures into shareable format |
| "What would Socrates ask about this note?" | Generates Socratic questioning to deepen understanding |

---

## Unique Ideas (The Secret Sauce)

### A. The "Gardening" Metaphor

Your vault is a garden. Voice commands use gardening language:
- **"Water the garden"** → Review and surface notes you haven't seen in a while (serendipity engine)
- **"Prune dead links"** → Find and fix broken `[[WikiLinks]]`
- **"Plant a seed"** → Create a stub note for a topic you want to explore later
- **"Cross-pollinate"** → Find connections between two seemingly unrelated notes
- **"Harvest"** → Compile a set of notes into an exportable document

### B. The Sleep-Dream-Mood Triangle

Voice Brain's most powerful insight comes from connecting:
- **Dream Journal** → sleep quality, subconscious themes, emotional processing
- **Daily Journal** → mood, energy, nutrition, social
- **Stats JSON** → derived correlations between all three

Example insight after 30 days:
> "You report vivid dreams 2.3x more often on days with >150mg caffeine. However, mood the following morning is 15% higher on those days. Your trade-off: caffeine boosts next-day mood but fragments sleep architecture."

### C. Voice-Activated Spaced Repetition

- "Quiz me on Rust"
- Finds your Rust notes, generates Q&A, asks them aloud (TTS optional)
- You answer verbally, it judges correctness
- Schedules next review based on performance

### D. The "Serendipity Spinner"

- "Surprise me"
- Randomly surfaces a note you haven't opened in 30+ days
- Gemma 4 explains *why* it might be relevant to your current projects

### E. Stats-Driven Morning Briefing

- "Brief me"
- Generates a 60-second spoken summary:
  - "Last night you slept 7.5 hours with 2 dreams. Readiness is 74. Your recommendation today: skip the second espresso. You have 3 open TODOs."

### F. Creative Velocity Tracking

- "How creative was I today?"
- Gemma 4 reads all notes you created outside the consumption folders and scores them on novelty, depth, connectivity, clarity, actionability
- Over weeks, builds a personal "creative rhythm" profile

### G. The Creativity-Sleep-Mood Triangle

The most powerful insight combines three signals:
- **Creative Output** → what you produced (notes, specs, ideas)
- **Sleep** → how well you recovered
- **Mood** → how you felt

Patterns that emerge:
- "Your best creative days follow 7.5+ hour sleep nights by 68%"
- "You write deeper notes on days you exercise before 9am"
- "Your idea capture spikes 2 days after high-social days — are you an introvert processor?"
- "Connectivity of your notes drops when mood is below 5 — you think in isolation when down"

### H. The "Am I Consuming or Creating?" Ratio

Voice Brain calculates a daily C/C ratio:
- **Consumption:** Journal entries + dream captures (words recorded about life)
- **Creation:** Notes produced in Projects, Resources, Inbox (words shaping ideas)

A healthy creator might aim for 1:1 or higher. A pure consumer might be 3:1 or worse.

### I. Stats-Driven Morning Briefing

- "Brief me"
- Generates a 60-second spoken summary:
  - "Last night you slept 7.5 hours with 2 dreams. Readiness is 74. Your recommendation today: skip the second espresso. You have 3 open TODOs."

### J. Dream Pattern Detection

After accumulating dream entries, Voice Brain can answer:
- "Do I dream about flying more when I'm stressed?"
- "What locations recur in my dreams?"
- "Connect my dreams to my mood the next day"

---

## Omarchy Integration

### Keybinding (Primary Activation)

File: `~/.config/hypr/bindings.lua`

```lua
-- Voice Brain — Push-to-talk voice assistant
-- Unbind if you ever need SUPER+ALT+V
o.bind("SUPER + ALT + V", "Voice Brain", "voice-brain --toggle")
```

> **Note:** Pick a chord that's comfortable to hold while speaking. `SUPER + ALT + V` (hold, speak, release) is ergonomic. `SUPER + V` conflicts with "Universal paste."

### Always-Available Mic Widget in Bar

**Visual states for bar widget:**
- 🎤 gray = idle
- 🎤 red pulse = recording
- 🧠 amber = processing with Gemma 4
- 💜 purple = dream detected
- 📊 blue = stats generated
- ✅ green = success
- ❌ red = error

### Hook: Auto-start on Login

```bash
omarchy hook install post-boot ~/.config/omarchy/hooks/post-boot.d/99-voice-brain.sh
```

Content of `99-voice-brain.sh`:

```bash
#!/bin/bash
# Start voice-brain daemon on desktop login
export GEMMA_MODEL=gemma3:9b
export WHISPER_MODEL=base
export VAULT_PATH="$HOME/Documents/Obsidian/Omarchy-Yev"
export DREAM_FOLDER="Dream Journal"
export JOURNAL_FOLDER="Journal"
export STATS_FOLDER="Stats"
exec voice-brain --daemon &
```

### Scheduled Stats Generation

```bash
# Add to user's crontab
(crontab -l 2>/dev/null; echo "59 23 * * * VAULT_PATH=$HOME/Documents/Obsidian/Omarchy-Yev GEMMA_MODEL=gemma3:9b /usr/bin/voice-brain --generate-stats --date today >> /tmp/voice-brain-cron.log 2>&1") | crontab -
```

### Window Rule (Float the Status Overlay)

File: `~/.config/hypr/hyprland.lua`:

```lua
-- Float the voice-brain status overlay
o.window("class:^(voice-brain)$", {
    float = true,
    size = "400x80",
    center = true,
    nofocus = true,
    pin = true,
    opacity = 0.9,
    border = false,
})
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        USER LAYER                             │
│  [SUPER+ALT+V] → Hold → Speak → Release                     │
└───────────────────────┬──────────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────────┐
│                     AUDIO CAPTURE                             │
│  PipeWire / parec → 16kHz mono WAV → 30s max buffer         │
│  VAD trims silence at start/end                              │
└───────────────────────┬──────────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────────┐
│              WHISPER (Local Speech-to-Text)                   │
│  faster-whisper / whisper.cpp                                 │
│  Model: base/small (balance of speed/accuracy)               │
│  ~50-500ms transcription on CPU                              │
└───────────────────────┬──────────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────────┐
│              TRIGGER DETECTOR (Regex + Keywords)              │
│  "I had a dream..." ──────▶ Dream Router                     │
│  "log this" ──────────────▶ Journal Router                   │
│  "generate stats" ────────▶ Stats Router                     │
│  (no match) ──────────────▶ General Command Router           │
└─────────────┬─────────────┬─────────────────┬────────────────┘
              │             │                 │
    ┌─────────▼────┐ ┌──────▼──────┐  ┌──────▼──────┐
    │ DREAM        │ │ JOURNAL     │  │ STATS       │
    │ JOURNAL      │ │ APPEND      │  │ GENERATOR   │
    │ SPLITTER     │ │ TO DAILY    │  │ (Gemma 4)   │
    └──────┬───────┘ └─────┬───────┘  └──────┬──────┘
           │               │                  │
┌──────────▼───────────────▼──────────────────▼──────────────┐
│              GEMMA 4 (Local LLM Engine)                     │
│  Ollama / llama.cpp — gemma3:4b or gemma3:9b               │
│  Functions: split_dreams, generate_title, extract_stats    │
│  Context window: 1M tokens (entire vault if needed)        │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│              OBSIDIAN VAULT (Filesystem)                     │
│  ~/Documents/Obsidian/Omarchy-Yev/                          │
│  ├── Dream Journal/    (auto-created)                       │
│  ├── Journal/          (auto-created)                       │
│  ├── Stats/            (auto-created)                       │
│  ├── Inbox/            (general captures)                   │
│  ├── Projects/         (active work)                        │
│  ├── Areas/            (ongoing responsibilities)           │
│  ├── Resources/        (reference material)                  │
│  └── (your existing folders)                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Gemma 4 + Whisper Model Selection

### Your Hardware
- Intel i7-9750H (6c/12t)
- 32 GB RAM
- AMD Radeon Pro 5500M (Navi 14, 4GB VRAM)
- No CUDA

### Recommended Whisper Models

| Model | Size | CPU Latency | Quality | Recommendation |
|-------|------|-------------|---------|----------------|
| `base` | 74MB | ~100ms | Good | ✅ **Day 1 choice** — fast, accurate enough |
| `small` | 244MB | ~300ms | Very Good | ✅ **Sweet spot** |
| `medium` | 769MB | ~1s | Excellent | If accuracy critical |

```python
from faster_whisper import WhisperModel
model = WhisperModel("base", device="cpu", compute_type="int8")
```

### Recommended Gemma 4 Models

| Model | Quant | RAM | Speed | Best For |
|-------|-------|-----|-------|----------|
| `gemma3:4b` | Q4_K_M | ~3GB | Fast | Quick queries, dream splitting |
| `gemma3:9b` | Q4_K_M | ~6GB | Medium | ✅ **Stats generation, creative assessment, reasoning** |
| `gemma3:9b` | Q8_0 | ~10GB | Medium | Heavy reasoning, full vault queries |

**For your 32GB machine:**
- Use `gemma3:9b` as default for stats generation and vault queries
- Use `gemma3:4b` for quick dream splitting and title generation
- For full-vault context (1M tokens), `gemma3:4b` may be necessary due to KV-cache memory

```bash
ollama pull gemma3:9b
ollama pull gemma3:4b
```

### Context Window Strategy

| Vault Size | Strategy |
|-----------|----------|
| < 100K tokens | Load entire vault into context |
| 100K – 500K tokens | Load vault + targeted file reads |
| 500K – 1M tokens | Use `gemma3:4b` to fit full vault |
| > 1M tokens | Sliding window: MOCs + recent + query results |

For most users, your entire vault fits in 1M context.

---

## Implementation Roadmap

### Phase 0: Foundation (2 hours)
- [ ] Install dependencies: `pip install faster-whisper ollama textual pyyaml`
- [ ] Pull models: `ollama pull gemma3:9b`, `ollama pull gemma3:4b`
- [ ] Test basic transcription + LLM pipeline
- [ ] Verify vault path: `~/Documents/Obsidian/Omarchy-Yev/`
- [ ] Create four folders if missing

### Phase 1: Core Voice Loop (2 hours)
- [ ] Audio capture via `parec` (PipeWire)
- [ ] Whisper transcription
- [ ] Trigger detection (dream / log / general)
- [ ] Omarchy notifications via `notify-send`

### Phase 2: Dream Journal (2 hours)
- [ ] Detect "I had a dream..." prefix
- [ ] Pass to Gemma 4 with splitting prompt
- [ ] Generate evocative titles
- [ ] Write to `Dream Journal/YYYY-MM-DD_{Title}.md`
- [ ] Handle multi-dream sessions

### Phase 3: Daily Journal (1 hour)
- [ ] Detect "log this" prefix
- [ ] Append to `Journal/YYYY-MM-DD.md` with timestamp
- [ ] Handle first-entry-of-day creation
- [ ] `---` separator between entries

### Phase 4: Stats Generator (3 hours)
- [ ] Collect today's entries (dreams + journal + creative output notes)
- [ ] Scan vault for notes created today outside special folders
- [ ] Pass qualifying notes to Gemma 4 for creativity assessment
- [ ] Load last 7 stats JSON files for trend context
- [ ] Pass to Gemma 4 with structured extraction prompt
- [ ] Parse and validate JSON output
- [ ] Save to `Stats/YYYY-MM-DD.json`
- [ ] Optional: Generate `.md` summary companion
- [ ] Cron job for auto-generation at 23:59

### Phase 5: Omarchy Polish (2 hours)
- [ ] Add `SUPER + ALT + V` keybinding
- [ ] Create bar widget status indicator
- [ ] Post-boot hook for daemon mode
- [ ] Window rule for float overlay

### Phase 6: Refinement (Ongoing)
- [ ] Wake-word detection ("Hey brain")
- [ ] TTS for responses (Piper)
- [ ] Stats dashboard (web view)
- [ ] Dream pattern analysis across weeks
- [ ] Correlation confidence scoring improvements
- [ ] Integration with wearable data (future)

---

## Project File Structure

```
voice-brain/
├── voice_brain/
│   ├── __init__.py
│   ├── main.py              # CLI entrypoint
│   ├── daemon.py            # Background daemon + HTTP API
│   ├── audio.py             # Capture, VAD, format handling
│   ├── stt.py               # Whisper integration
│   ├── llm.py               # Gemma 4 / Ollama client
│   ├── intent.py            # Trigger detection + command routing
│   ├── vault.py             # Vault filesystem ops + auto-folder creation
│   ├── dream_journal.py     # Dream splitting, title generation, writing
│   ├── daily_journal.py     # Daily append, timestamp, separators
│   ├── stats_generator.py   # Stats JSON generation + validation
│   ├── creative_output.py       # Vault scan, creativity assessment, scoring
│   ├── stats_schema.py      # JSON schema validation + defaults
│   ├── organizer.py         # Move, tag, link operations
│   ├── templates.py         # Template engine
│   ├── config.py            # Settings, vault path, model selection
│   └── omarchy.py           # Omarchy integration
│
├── templates/
│   ├── book-summary.md
│   ├── meeting-notes.md
│   ├── project-spec.md
│   ├── daily-journal.md
│   └── dream-journal.md
│
├── config/
│   └── default.yaml
│
├── pyproject.toml
├── README.md
├── install.sh               # One-line Omarchy setup
└── voice-brain.desktop      # Desktop entry
```

---

## Configuration (config/default.yaml)

```yaml
vault:
  path: "~/Documents/Obsidian/Omarchy-Yev"
  inbox: "Inbox"
  daily_format: "Daily/YYYY-MM-DD"
  auto_create_folders: true
  folders:
    dream: "Dream Journal"
    journal: "Journal"
    stats: "Stats"

audio:
  device: "default"
  sample_rate: 16000
  channels: 1
  format: "s16le"
  max_recording_seconds: 60
  vad_threshold: 0.5
  vad_min_silence: 0.5

stt:
  model: "base"
  device: "cpu"
  compute_type: "int8"
  language: "en"

llm:
  provider: "ollama"
  model: "gemma3:9b"
  model_quick: "gemma3:4b"       # For fast tasks: dream splitting, title gen
  context_window: 128000
  temperature_default: 0.7
  temperature_stats: 0.3          # Lower = more deterministic JSON
  max_tokens: 8000

dream_journal:
  enabled: true
  triggers:
    - "I had a dream"
    - "I dreamed about"
    - "In my dream"
    - "Last night I dreamt"
    - "There was this dream"
  split_prompt_version: "1.0.0"
  auto_title: true
  title_max_words: 6
  frontmatter_template: |
    ---
    dream_id: "{{dream_id}}"
    dreamt_at: "{{dreamt_at}}"
    recorded_at: "{{recorded_at}}"
    title: "{{title}}"
    vividness: {{vividness}}
    lucidity: {{lucidity}}
    themes: {{themes}}
    emotional_tone: "{{emotional_tone}}"
    tags:
      - dream
    created_by: voice-brain
    model: {{model}}
    ---

daily_journal:
  enabled: true
  triggers:
    - "log this"
    - "log that"
    - "journal this"
    - "remember this"
  entry_separator: "---"
  timestamp_format: "HH:mm"
  frontmatter_template: |
    ---
    date: "{{date}}"
    created_by: voice-brain
    entry_count: {{entry_count}}
    ---

stats:
  enabled: true
  triggers:
    - "generate stats"
    - "how was my day"
    - "analyze my week"
  auto_generate_at: "23:59"
  history_days: 7
  generate_markdown_summary: true
  schema_version: "1.0.0"
  categories:
    - sleep
    - mood
    - energy
    - physical
    - nutrition
    - cognitive
    - creative_output
    - social
    - environment
    - habits
    - time_use

creative_output:
  enabled: true
  # Folders that DON'T count as creative output
  excluded_folders:
    - "Dream Journal"
    - "Journal"
    - "Stats"
  # These ARE creative even though system-created
  included_folders:
    - "Inbox"
    - "Projects"
    - "Resources"
    - "Areas"
    - "Archive"
    - "Daily"
  # Dimensions Gemma 4 assesses
  dimensions:
    - novelty
    - depth
    - connectivity
    - clarity
    - actionability
  min_note_length_words: 10     # Skip tiny captures
  track_word_count: true
  track_domains: true
  track_formats: true
  assess_quality: true          # Run Gemma 4 quality analysis
  creativity_score_unit: "0-100"

omarchy:
  keybinding: "SUPER + ALT + V"
  notifications: true
  bar_widget: true
  osd_feedback: true

commands:
  create_note:
    default_folder: "Inbox"

  organize:
    dry_run_by_default: true
    min_confidence: 0.7

features:
  auto_tag: true
  auto_link: true
  daily_notes: true
  moc_generation: true
  serendipity: true
  spaced_repetition: false
```

---

## Dependencies to Install

### System Packages

```bash
# Audio
omarchy pkg add pipewire pipewire-pulse pipewire-alsa

# Python
omarchy pkg add python python-pip python-virtualenv

# Cron (usually pre-installed, verify)
pacman -S cronie
systemctl enable cronie --now
```

### Python Packages

```bash
pip install faster-whisper ollama textual pyyaml python-dateutil jsonschema pydantic

# Optional: VAD
pip install webrtcvad-wheels

# Optional: TTS
pip install piper-tts
```

### Ollama Models

```bash
ollama pull gemma3:9b
ollama pull gemma3:4b
```

---

## Performance Expectations on Your Hardware

| Operation | Expected Time | Notes |
|-----------|--------------|-------|
| Audio capture → Whisper (base) | 100-200ms | Almost instant |
| Trigger detection | 1ms | Regex |
| Dream splitting (Gemma 4b) | 1-3s | Fast model, simple prompt |
| Title generation (Gemma 4b) | 1-2s | Fast |
| Journal append | < 50ms | File I/O |
| Creative output scan + assess (Gemma 9b) | 10-20s | Depends on note count |
| Stats generation (Gemma 9b) | 20-40s | Reads all day's entries + 7 days history + creative notes |
| File write operations | < 50ms | Instant |

**Dream capture round-trip:** 2-5 seconds from releasing the key to file appearing.
**Stats generation:** ~30 seconds — acceptable for a daily batch job.

---

## Security & Privacy Notes

- **Zero network calls for inference** — everything runs locally via Ollama
- **Whisper models are local** — no audio leaves your machine
- **Vault stays on disk** — LLM reads files, nothing is uploaded
- **No telemetry** — build it without any analytics/tracking
- **Sensitive notes** — consider a `.voice-brain-ignore` file for private notes
- **Stats JSON is local** — your biometric data never leaves your laptop

---

## Future Extensions

1. **Morning briefing mode** — "Brief me" reads sleep + today's calendar + open TODOs
2. **Stats dashboard** — Web UI with charts (Chart.js) showing trends over time
3. **Wearable integration** — Import Apple Health, Oura, WHOOP data to merge with subjective stats
4. **Voice-driven weather/mood correlation** — "Do I feel worse on rainy days?"
5. **Dream lucidity training** — Track lucidity frequency, suggest reality-check reminders
6. **Mobile companion** — Record dreams via phone on waking, sync to laptop vault
7. **Seasonal pattern detection** — "How does my mood change with daylight hours?"
8. **Dietary trigger detection** — "What foods correlate with poor sleep?"
9. **Social battery tracker** — "How much social interaction is my sweet spot?"
10. **Export to CSV/Parquet** — For analysis in Pandas, R, or Excel
11. **Creative pattern analysis** — "Am I more creative after coffee or after exercise?"
12. **Note connectivity health** — Track graph density over time as a wellbeing proxy

---

## One-Liner Pitch for the README

> **Voice Brain** is a local, open-source voice assistant for your Obsidian vault that captures dreams, logs your day, and auto-generates a quantified-self JSON dataset — no cloud, no subscriptions, no typing. Talk to your brain. Understand yourself.

---

## Example Day in the Life

### 07:15 — Morning Dream Capture
```
[Hold SUPER+ALT+V]
"I had a dream where I was flying over a neon city... then I had another dream where everyone at work was a cat and I was the only human..."
[Release]

🔔 Voice Brain: 💜 2 dreams saved
   Dream Journal/2025-01-15_Flying_Over_the_Neon_City.md
   Dream Journal/2025-01-15_Workplace_Cat_Dystopia.md
```

### 08:20 — Morning Journal
```
[Hold SUPER+ALT+V]
"log this: great workout this morning, deadlifts felt strong but lower back a bit tight. Mood is 8 out of 10."
[Release]

🔔 Voice Brain: 📝 Logged to Journal/2025-01-15.md
```

### 15:45 — Afternoon Log
```
[Hold SUPER+ALT+V]
"log this: hit a wall at 3pm, too much coffee I think. Took a walk, feeling better. Mood dropped to 5 now back to 6."
[Release]
```

### 22:00 — Evening Log
```
[Hold SUPER+ALT+V]
"log this: good stir-fry for dinner, lots of veg. Planning to read before bed instead of screens. Today's been solid overall."
[Release]
```

### 13:30 — Creative Work
```
[Hold SUPER+ALT+V]
"Create a new note on Rust async patterns I just figured out"
[Release]

🔔 Voice Brain: ✅ Created Resources/Rust_Async_Patterns.md
   Tags: #rust #programming #async
```

### 16:00 — More Creative Output
```
[Hold SUPER+ALT+V]
"Start a project spec for the landing page API"
[Release]

🔔 Voice Brain: ✅ Created Projects/Landing_Page_API_Spec.md
```

### 23:59 — Auto Stats (or manual trigger)
```
[Hold SUPER+ALT+V]
"generate stats"
[Release]

🔔 Voice Brain: 📊 Stats/2025-01-15.json generated
   Readiness: 74/100 | Wellbeing: 7.1/10 | Creative Output: 66/100
   Notes produced today: 4 (1,450 words)
   Domains: programming, project-management, ideas
   Peak creative time: 09:00-11:00
   Top recommendation: Cut caffeine after 11am
```

### Next Morning — Brief Me
```
[Hold SUPER+ALT+V]
"brief me"
[Release]

🔔 Voice Brain: 🌅 Good morning.
   Sleep: 7.5h, 2 dreams, quality 72/100
   Readiness: 74/100
   Today's tip: Skip the second espresso. You crashed yesterday.
   Open TODOs: 3
```

---

*This document is the design spec. Build the repo. Ship it. Understand yourself.*
