/** Dashboard view: radar of today's categories + 30-day readiness/creativity trend.
 *  Pure SVG — no chart dependencies. */

import { ItemView, WorkspaceLeaf, TFile } from "obsidian";
import type VoiceBrainPlugin from "../../main";

export const VIEW_TYPE_VB_DASHBOARD = "voice-brain-dashboard";

interface DayStat { date: string; readiness: number | null; creativity: number | null; }

export class DashboardView extends ItemView {
  constructor(leaf: WorkspaceLeaf, private plugin: VoiceBrainPlugin) {
    super(leaf);
  }

  getViewType(): string { return VIEW_TYPE_VB_DASHBOARD; }
  getDisplayText(): string { return "Voice Brain Dashboard"; }
  getIcon(): string { return "mic"; }

  async onOpen(): Promise<void> { await this.render(); }

  async render(): Promise<void> {
    const el = this.contentEl;
    el.empty();
    el.addClass("vb-dashboard");
    const s = this.plugin.settings;

    // gather last 30 days of stats
    const days: DayStat[] = [];
    let latest: any = null;
    let latestDate = "";
    for (let i = 0; i < 30; i++) {
      const date = new Date(Date.now() - i * 86400_000).toISOString().slice(0, 10);
      const f = this.app.vault.getAbstractFileByPath(`${s.statsFolder}/${date}.json`);
      if (f instanceof TFile) {
        try {
          const doc = JSON.parse(await this.app.vault.read(f));
          days.push({
            date,
            readiness: doc.derived?.readiness_score ?? null,
            creativity: doc.creative_output?.creativity_score ?? null,
          });
          if (i < 1 || !latest) { latest = doc; latestDate = date; }
        } catch { /* corrupted, skip */ }
      }
    }
    days.sort((a, b) => a.date.localeCompare(b.date));

    if (!latest) {
      el.createEl("p", {
        text: "No stats yet. Say \"generate stats\" (or run the nightly timer) to populate the dashboard.",
      });
      return;
    }

    el.createEl("h2", { text: `Voice Brain — ${latestDate}` });
    const row = el.createEl("div", { cls: "vb-dash-row" });
    row.createEl("div", { cls: "vb-radar-wrap" }).innerHTML = this.radarSvg(latest);
    const right = row.createEl("div", { cls: "vb-trend-wrap" });
    right.createEl("h3", { text: "30-day trend" });
    right.innerHTML += this.trendSvg(days);

    const meta = el.createEl("div", { cls: "vb-dash-meta" });
    meta.innerHTML = [
      `<b>Archetype:</b> ${latest.derived?.archetype ?? "—"}`,
      `<b>Day type:</b> ${latest.derived?.day_type ?? "—"}`,
      `<b>Capture streak:</b> ${this.plugin.brain.captureStreak()} days`,
      `<b>Readiness:</b> ${latest.derived?.readiness_score ?? "—"}/100`,
    ].join(" · ");

    const narrative = el.createEl("p", { cls: "vb-narrative" });
    narrative.setText(latest.insights?.narrative ?? "");
  }

  private radarSvg(doc: any): string {
    const cats = ["sleep", "mood", "energy", "physical", "nutrition", "cognitive",
                  "social", "habits"];
    const scores = cats.map((c) => {
      const node = doc[c] ?? {};
      for (const key of ["quality_score", "average_score", "subjective_rating",
                         "focus_score", "dietary_quality_score"]) {
        const v = node[key];
        if (typeof v === "number") return v > 10 ? v : v * 10;
      }
      return 0;
    });
    const cx = 130, cy = 130, r = 100;
    const point = (i: number, scale: number) => {
      const angle = (Math.PI * 2 * i) / cats.length - Math.PI / 2;
      return `${cx + Math.cos(angle) * r * scale},${cy + Math.sin(angle) * r * scale}`;
    };
    const grid = [0.25, 0.5, 0.75, 1].map((scale) =>
      `<polygon points="${cats.map((_, i) => point(i, scale)).join(" ")}" class="vb-grid" />`).join("");
    const labels = cats.map((c, i) => {
      const [x, y] = point(i, 1.18).split(",");
      return `<text x="${x}" y="${y}" class="vb-label" text-anchor="middle">${c}</text>`;
    }).join("");
    const poly = `<polygon points="${scores.map((v, i) => point(i, Math.max(0.05, v / 100))).join(" ")}" class="vb-radar" />`;
    return `<svg viewBox="0 0 260 260" width="260" height="260">${grid}${poly}${labels}</svg>`;
  }

  private trendSvg(days: DayStat[]): string {
    const w = 500, h = 160, pad = 24;
    const maxPoints = 30;
    const pts = days.slice(-maxPoints);
    const x = (i: number) => pad + (i / Math.max(1, pts.length - 1)) * (w - 2 * pad);
    const y = (v: number) => h - pad - (v / 100) * (h - 2 * pad);
    const line = (key: "readiness" | "creativity") =>
      pts.map((d, i) => (d[key] === null ? null : `${x(i)},${y(d[key]!)}`)).filter(Boolean).join(" ");
    return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">
      <line x1="${pad}" y1="${y(100)}" x2="${w - pad}" y2="${y(100)}" class="vb-grid-line" />
      <polyline points="${line("readiness")}" class="vb-line-readiness" />
      <polyline points="${line("creativity")}" class="vb-line-creativity" />
      <text x="${pad}" y="${pad - 6}" class="vb-label">readiness (blue) · creativity (purple)</text>
    </svg>`;
  }
}
