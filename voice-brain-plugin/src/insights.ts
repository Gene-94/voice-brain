/** Deterministic insights engine (ported from Python). The LLM narrates; code calculates. */

export function pearson(xs: number[], ys: number[]): number | null {
  const n = xs.length;
  if (n < 3) return null;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let dx2 = 0;
  let dy2 = 0;
  for (let i = 0; i < n; i++) {
    const dx = xs[i] - mx;
    const dy = ys[i] - my;
    num += dx * dy;
    dx2 += dx * dx;
    dy2 += dy * dy;
  }
  const den = Math.sqrt(dx2 * dy2);
  if (den === 0) return null;
  return Math.round((num / den) * 100) / 100;
}

export function zscore(value: number, series: number[]): number | null {
  if (series.length < 3) return null;
  const mean = series.reduce((a, b) => a + b, 0) / series.length;
  const variance = series.reduce((a, x) => a + (x - mean) ** 2, 0) / series.length;
  const sd = Math.sqrt(variance);
  if (sd === 0) return null;
  return Math.round(((value - mean) / sd) * 100) / 100;
}

function extract(doc: any, dotted: string): number | null {
  let node: any = doc;
  for (const part of dotted.split(".")) {
    if (node == null || typeof node !== "object") return null;
    node = node[part];
  }
  return typeof node === "number" ? node : null;
}

const CORRELATION_PAIRS: Array<[string, string, string, string]> = [
  ["sleep.quality_score", "derived.wellbeing_index", "sleep quality", "wellbeing"],
  ["sleep.quality_score", "creative_output.creativity_score", "sleep quality", "creativity"],
  ["physical.exercise.did_exercise", "mood.average_score", "exercise", "mood"],
  ["nutrition.caffeine_mg_estimate", "energy.afternoon", "caffeine", "afternoon energy"],
];

export function computeCorrelations(history: any[], minDays = 5): any[] {
  const out: any[] = [];
  for (const [a, b, la, lb] of CORRELATION_PAIRS) {
    const xs: number[] = [];
    const ys: number[] = [];
    for (const doc of history) {
      const va = extract(doc, a);
      const vb = extract(doc, b);
      if (va !== null && vb !== null) {
        xs.push(va);
        ys.push(vb);
      }
    }
    if (xs.length >= minDays) {
      const r = pearson(xs, ys);
      if (r !== null && Math.abs(r) >= 0.3) {
        out.push({
          factor_a: la,
          factor_b: lb,
          relationship: r > 0 ? "positive" : "negative",
          strength: r,
          n_day_support: xs.length,
          notes: `Deterministic Pearson r over ${xs.length} days.`,
        });
      }
    }
  }
  return out;
}

export function computeTrend(today: any, history: any[]): any {
  const ys = history
    .map((h) => extract(h, "derived.readiness_score"))
    .filter((v): v is number => v !== null);
  const todays = extract(today, "derived.readiness_score");
  const out: any = { trending: "unknown", trend_explanation: "Not enough history yet." };
  if (ys.length >= 2 && todays !== null) {
    const prev = ys[ys.length - 1];
    const delta = Math.round(todays - prev);
    if (Math.abs(delta) < 5) {
      out.trending = "stable";
      out.trend_explanation = `Readiness stable vs yesterday (${prev}).`;
    } else {
      out.trending = `${delta > 0 ? "up" : "down"}_${Math.abs(delta)}pts`;
      out.trend_explanation = `Readiness ${delta > 0 ? "up" : "down"} ${Math.abs(delta)} pts vs yesterday (${prev}).`;
    }
  }
  const z = todays !== null ? zscore(todays, ys) : null;
  if (z !== null && Math.abs(z) >= 2) {
    out.anomaly_flag = `Readiness is a ${z}σ outlier vs your recent baseline.`;
  }
  return out;
}

export function ccRatio(journalWords: number, creativeWords: number): any {
  const ratio = creativeWords > 0 ? Math.round((journalWords / creativeWords) * 100) / 100 : null;
  return {
    consumed_words: journalWords,
    created_words: creativeWords,
    cc_ratio: ratio,
    cc_ratio_note: ratio && ratio > 2 ? "Healthy ~1:1. You are logging more than producing." : null,
  };
}

export function captureStreak(statDays: Set<string>, journalDays: Set<string>, today: string): number {
  const days = new Set([...statDays, ...journalDays]);
  let streak = 0;
  const d = new Date(today + "T00:00:00");
  while (days.has(d.toISOString().slice(0, 10))) {
    streak++;
    d.setDate(d.getDate() - 1);
  }
  return streak;
}

export function precomputeBlock(today: any, history: any[], journalWords: number,
                               creativeWords: number, statDays: Set<string>,
                               journalDays: Set<string>, todayDate: string,
                               minDays = 5): any {
  return {
    correlations: computeCorrelations(history, minDays),
    trend: computeTrend(today, history),
    cc_ratio: ccRatio(journalWords, creativeWords),
    capture_streak_days: captureStreak(statDays, journalDays, todayDate),
    rule: "Use these numbers exactly. Do not recompute or invent statistics.",
  };
}
