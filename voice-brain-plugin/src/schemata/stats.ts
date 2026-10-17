/** Voice Brain Stats Schema v1.0.0 validation (ported from Python). */

export const CATEGORIES = ["sleep", "mood", "energy", "physical", "nutrition", "cognitive",
  "creative_output", "social", "environment", "habits", "time_use"];

const SCALE_100 = new Set(["readiness_score", "quality_score", "creativity_score", "focus_score",
  "productivity_score", "dietary_quality_score", "completeness_score"]);
const SCALE_10 = new Set(["subjective_rating", "average_score", "fatigue_level", "anxiety_level",
  "depression_screen", "mental_clarity", "wellbeing_index", "novelty_average", "depth_average",
  "connectivity_average", "clarity_average", "actionability_average", "loneliness_score",
  "perceived_exertion", "sleep_hygiene_score"]);

export function validateStats(doc: any): string[] {
  if (typeof doc !== "object" || doc === null || Array.isArray(doc)) {
    return ["top-level must be a JSON object"];
  }
  const errors: string[] = [];

  for (const key of ["date", "generated_at", "derived", "insights"]) {
    if (!(key in doc)) errors.push(`missing required top-level key '${key}'`);
  }
  if (doc.date && !/^\d{4}-\d{2}-\d{2}$/.test(String(doc.date))) {
    errors.push("'date' must be YYYY-MM-DD");
  }

  for (const cat of CATEGORIES) {
    const node = doc[cat];
    if (typeof node !== "object" || node === null) {
      errors.push(`category '${cat}' missing or not an object`);
      continue;
    }
    if (!("notes" in node)) errors.push(`${cat}.notes is required (1-3 sentences)`);
    if (!("source" in node)) errors.push(`${cat}.source is required (traceability)`);
  }

  const checkScales = (node: any, prefix: string) => {
    if (typeof node !== "object" || node === null) return;
    for (const [key, val] of Object.entries(node)) {
      if (typeof val !== "number") continue;
      if (SCALE_100.has(key) && (val < 0 || val > 100)) errors.push(`${prefix}${key}=${val} must be 0-100`);
      if (SCALE_10.has(key) && (val < 0 || val > 10)) errors.push(`${prefix}${key}=${val} must be 0-10`);
    }
  };
  for (const cat of [...CATEGORIES, "derived", "insights"]) checkScales(doc[cat], `${cat}.`);

  const derived = doc.derived;
  if (typeof derived === "object" && derived !== null) {
    if (!("readiness_score" in derived)) errors.push("derived.readiness_score is required (0-100)");
    const recs = derived.recommendations;
    if (!Array.isArray(recs)) errors.push("derived.recommendations is required (list)");
    else if (recs.length === 0) {
      errors.push("derived.recommendations must not be empty — cite at least one evidence-based action");
    }
  }
  const insights = doc.insights;
  if (typeof insights === "object" && insights !== null) {
    if (!String(insights.narrative ?? "").trim()) {
      errors.push("insights.narrative is required (2-3 sentence human story)");
    }
  }
  return errors;
}
