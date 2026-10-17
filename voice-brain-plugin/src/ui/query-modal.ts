/** Query modal: ask a question, get a markdown answer with clickable [[wikilinks]]. */

import { App, MarkdownRenderer, Modal, TFile, Notice } from "obsidian";
import type VoiceBrainPlugin from "../../main";

export class QueryModal extends Modal {
  private inputEl!: HTMLInputElement;
  private answerEl!: HTMLElement;

  constructor(app: App, private plugin: VoiceBrainPlugin, private presetQuestion?: string) {
    super(app);
  }

  onOpen(): void {
    this.titleEl.setText("Ask your brain");
    this.contentEl.empty();
    this.contentEl.addClass("vb-query-modal");

    this.inputEl = this.contentEl.createEl("input", { type: "text", cls: "vb-query-input" });
    this.inputEl.placeholder = "What do I know about…?";
    this.answerEl = this.contentEl.createEl("div", { cls: "vb-answer" });
    const hint = this.contentEl.createEl("div", { cls: "vb-modal-hint" });
    hint.setText("Answers cite notes as [[wikilinks]] · Enter to ask");

    this.inputEl.addEventListener("keydown", async (e) => {
      if (e.key === "Enter") await this.ask();
    });
    if (this.presetQuestion) {
      this.inputEl.value = this.presetQuestion;
      void this.ask();
    } else {
      this.inputEl.focus();
    }
  }

  private async ask(): Promise<void> {
    const question = this.inputEl.value.trim();
    if (!question) return;
    this.answerEl.empty();
    this.answerEl.createEl("p", { text: "🧠 Thinking…" });
    try {
      const answer = await this.plugin.brain.query(question);
      this.answerEl.empty();
      await MarkdownRenderer.render(this.app, answer, this.answerEl, "", this.plugin);
      // save answer action
      const saveEl = this.answerEl.createEl("div", { cls: "vb-save-row" });
      const btn = saveEl.createEl("button", { text: "Save as note" });
      btn.onclick = async () => {
        const { saveAnswer } = await import("../routes/query");
        const path = await saveAnswer(this.plugin.deps(), question, answer);
        new Notice(`Saved: ${path}`);
      };
    } catch (e: any) {
      this.answerEl.empty();
      this.answerEl.createEl("p", {
        text: `❌ ${String(e?.message ?? e)}`,
        cls: "vb-error",
      });
    }
  }
}

/** Open the latest stats JSON in a modal — quick "how was my day" view. */
export function openStatsQuickView(app: App, plugin: VoiceBrainPlugin): void {
  const s = plugin.settings;
  const day = new Date(Date.now() - 86400_000).toISOString().slice(0, 10);
  const file = app.vault.getAbstractFileByPath(`${s.statsFolder}/${day}.json`);
  if (!(file instanceof TFile)) {
    new Notice(`No stats for ${day}. Say "generate stats" first.`);
    return;
  }
  const modal = new Modal(app);
  modal.titleEl.setText(`Stats — ${day}`);
  void app.vault.read(file).then(async (text) => {
    const doc = JSON.parse(text);
    const md = [
      `**Readiness:** ${doc.derived?.readiness_score ?? "—"}/100 · **Wellbeing:** ${doc.derived?.wellbeing_index ?? "—"}/10 · **Archetype:** ${doc.derived?.archetype ?? "—"}`,
      "",
      `> ${doc.insights?.narrative ?? ""}`,
      "",
      ...(doc.derived?.recommendations ?? []).map((r: any, i: number) =>
        `${i + 1}. **${r.action}** — ${r.rationale} (${Math.round((r.confidence ?? 0) * 100)}%)`),
    ].join("\n");
    await MarkdownRenderer.render(app, md, modal.contentEl, "", plugin);
  });
  modal.open();
}
