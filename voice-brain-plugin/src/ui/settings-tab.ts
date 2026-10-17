/** Settings tab — the control center.
 *
 *  Synced sections write to Voice Brain Settings/settings.md + patterns.md in
 *  the vault: LiveSync carries them to every device, the Python daemon (and
 *  through it the phone) hot-reloads them, and the plugin follows them too.
 *  Local sections (Ollama URL, folders, server) stay in this device's data.json. */

import { App, Notice, PluginSettingTab, Setting } from "obsidian";
import type VoiceBrainPlugin from "../../main";
import { PATTERNS_PATH } from "../patterns";
import {
  readSyncedSettings, writeSyncedSettings, type SyncedValues,
} from "../settings-file";

const ROUTES = ["dream", "journal", "note", "capture", "query", "stats", "brief", "scratch"] as const;

const WHISPER_MODELS = ["small", "medium", "large-v3", "base", "base.en", "tiny.en"];

const labels: Record<string, string> = {
  dreamFolder: "Dream folder",
  journalFolder: "Journal folder",
  statsFolder: "Stats folder",
  inboxFolder: "Inbox folder",
};

export class VoiceBrainSettingTab extends PluginSettingTab {
  constructor(app: App, private plugin: VoiceBrainPlugin) {
    super(app, plugin);
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();
    const s = this.plugin.settings;

    containerEl.createEl("h2", { text: "Voice Brain" });
    containerEl.createEl("p", {
      text: "Control center for phone + laptop. Synced sections live in your vault " +
        "(Voice Brain Settings/) and reach every device through LiveSync — the daemon " +
        "picks them up on the next capture, no restart needed.",
      cls: "setting-item-description",
    });

    void this.renderSynced(containerEl);
    this.renderPatterns(containerEl);
    this.renderLocal(containerEl, s);
  }

  // ------------------------------------------------------------------ synced

  private async renderSynced(containerEl: HTMLElement): Promise<void> {
    const synced = await readSyncedSettings(this.app);
    const models = await this.plugin.ollama.listModels().catch(() => [] as string[]);

    new Setting(containerEl).setName("Models (synced)").setHeading();
    const save = async (updates: SyncedValues) => {
      await writeSyncedSettings(this.app, updates);
      // the plugin itself follows the synced values immediately
      if (updates.deep_model) this.plugin.settings.modelDeep = updates.deep_model;
      if (updates.quick_model) this.plugin.settings.modelQuick = updates.quick_model;
      await this.plugin.saveSettings();
      new Notice("Synced to all devices");
    };

    const modelDropdown = (name: string, desc: string, current: string,
                            key: "deep_model" | "quick_model") => {
      const setting = new Setting(containerEl).setName(name).setDesc(desc);
      if (models.length === 0) {
        setting.setDesc(`${desc} — Ollama unreachable; type the name`);
        setting.addText((t) => t.setValue(current).onChange(
          async (v) => await save({ [key]: v })));
        return;
      }
      const opts = models.includes(current) ? models : [current, ...models];
      setting.addDropdown((dd) => {
        dd.addOption("", "— choose —");
        for (const m of opts) dd.addOption(m, m);
        dd.setValue(current);
        dd.onChange(async (v) => await save({ [key]: v }));
      });
    };
    modelDropdown("Deep-lane model", "Reasoning: notes, stats, queries",
      synced.deep_model ?? this.plugin.settings.modelDeep, "deep_model");
    modelDropdown("Quick-lane model", "Fast tasks: dream splitting, tags, intent",
      synced.quick_model ?? this.plugin.settings.modelQuick, "quick_model");

    new Setting(containerEl)
      .setName("Use one model for everything")
      .setDesc("Mirrors the deep-lane model into the quick lane.")
      .addToggle((tg) => {
        tg.setValue(synced.deep_model === synced.quick_model);
        tg.onChange(async (on) => {
          if (on) await save({ quick_model: synced.deep_model ?? this.plugin.settings.modelDeep });
          else await save({
            quick_model: models.find((m) => m.includes("4b"))
              ?? synced.quick_model ?? this.plugin.settings.modelQuick,
          });
          this.display();
        });
      });
    new Setting(containerEl).addButton((b) => {
      b.setButtonText("Refresh model list");
      b.onClick(() => this.display());
    });

    new Setting(containerEl).setName("Voice & capture (synced)").setHeading();
    new Setting(containerEl).setName("Spoken language")
      .setDesc("auto detects per capture (recommended); pin a language if it mis-detects.")
      .addDropdown((dd) => {
        dd.addOption("auto", "Auto-detect (en / pt / ru)");
        dd.addOption("en", "English");
        dd.addOption("pt", "Português");
        dd.addOption("ru", "Русский");
        dd.setValue(synced.stt_language ?? "auto");
        dd.onChange(async (v) => {
          await writeSyncedSettings(this.app, { stt_language: v });
          this.plugin.settings.language = v;
          await this.plugin.saveSettings();
          new Notice("Language synced");
        });
      });
    new Setting(containerEl).setName("Whisper model")
      .setDesc("small is a good multilingual default; .en models are English-only.")
      .addDropdown((dd) => {
        const current = synced.stt_model ?? this.plugin.settings.whisperModel;
        const opts = WHISPER_MODELS.includes(current) ? WHISPER_MODELS : [current, ...WHISPER_MODELS];
        for (const m of opts) dd.addOption(m, m);
        dd.setValue(current);
        dd.onChange(async (v) => {
          await writeSyncedSettings(this.app, { stt_model: v });
          this.plugin.settings.whisperModel = v;
          await this.plugin.saveSettings();
          new Notice("Whisper model synced");
        });
      });
    new Setting(containerEl).setName("Laptop capture overlay")
      .setDesc("What SUPER+ALT+V shows while recording.")
      .addDropdown((dd) => {
        dd.addOption("overlay", "Overlay box (translucent)");
        dd.addOption("notify", "Desktop notification only");
        dd.addOption("none", "Nothing (silent)");
        dd.setValue(synced.overlay ?? "overlay");
        dd.onChange(async (v) => {
          await writeSyncedSettings(this.app, { overlay: v });
          new Notice("Capture UI synced");
        });
      });
    new Setting(containerEl).setName("Silence auto-stop (ms)")
      .setDesc("Laptop mic: silence that ends a capture. 0 = manual send (like the phone).")
      .addText((t) => {
        t.setValue(String(synced.silence_stop_ms ?? "1200"));
        t.onChange(async (v) => {
          const n = parseInt(v.replace(/\D/g, ""), 10);
          if (!Number.isNaN(n)) await writeSyncedSettings(this.app, { silence_stop_ms: String(n) });
        });
      });
  }

  // ------------------------------------------------------------------ patterns

  private renderPatterns(containerEl: HTMLElement): void {
    new Setting(containerEl).setName("Speech patterns (synced)").setHeading();
    containerEl.createEl("p", {
      text: "First match wins, top to bottom. Applies to the laptop hotkey, the phone " +
        "and this plugin — one list everywhere. Saving drops comments in the file " +
        "(rules themselves are kept); hand-editing the file still works.",
      cls: "setting-item-description",
    });

    const listEl = containerEl.createEl("div", { cls: "voice-brain-pattern-list" });
    const rules: { pattern: string; route: string; folder: string }[] = [];

    void (async () => {
      const file = this.app.vault.getAbstractFileByPath(PATTERNS_PATH);
      if (file) {
        const text = await this.app.vault.read(file as any);
        for (const raw of text.split("\n")) {
          const line = raw.trim();
          if (!line || line.startsWith("#")) continue;
          const [pattern, route, folder] = line.split("|").map((p) => p.trim());
          if (!pattern || !ROUTES.includes(route as any)) continue;
          rules.push({ pattern, route, folder: folder ?? "" });
        }
      }
      this.renderPatternRows(listEl, rules);

      new Setting(containerEl).addButton((b) => {
        b.setButtonText("Add pattern");
        b.setCta();
        b.onClick(() => {
          rules.push({ pattern: "new pattern", route: "note", folder: "" });
          this.renderPatternRows(listEl, rules);
        });
      }).addButton((b) => {
        b.setButtonText("Save patterns");
        b.onClick(async () => {
          const lines = rules
            .filter((r) => r.pattern.trim() && r.route)
            .map((r) => [r.pattern, r.route, r.folder].filter(Boolean).join("|"));
          const body = [
            "# Voice Brain — trigger patterns",
            "",
            "# One per line: pattern | route | folder (regex, first match wins).",
            "# Routes: dream, journal, note, capture, query, stats, brief, scratch.",
            "",
            ...lines,
            "",
          ].join("\n");
          const file = this.app.vault.getAbstractFileByPath(PATTERNS_PATH);
          if (file) await this.app.vault.modify(file as any, body);
          else await this.app.vault.create(PATTERNS_PATH, body);
          // bust the plugin's own pattern cache (Brain re-reads on mtime change,
          // but force it so the very next capture uses the new rules)
          await this.plugin.brain?.patterns.rules();
          new Notice(`Saved ${lines.length} patterns — synced to all devices`);
        });
      });
    })();
  }

  private renderPatternRows(
    listEl: HTMLElement,
    rules: { pattern: string; route: string; folder: string }[],
  ): void {
    listEl.empty();
    rules.forEach((rule, i) => {
      const row = listEl.createEl("div", { cls: "voice-brain-pattern-row" });
      row.createEl("input", {
        type: "text", value: rule.pattern,
        attr: { placeholder: "e.g. tenho uma ideia", style: "flex: 2; min-width: 12em;" },
      }).addEventListener("change", (e) => {
        rule.pattern = (e.target as HTMLInputElement).value;
      });
      const select = row.createEl("select", { attr: { style: "flex: 1;" } });
      for (const r of ROUTES) {
        const opt = select.createEl("option", { text: r });
        if (r === rule.route) opt.selected = true;
      }
      select.addEventListener("change", () => { rule.route = select.value; });
      row.createEl("input", {
        type: "text", value: rule.folder,
        attr: { placeholder: "folder (note route)", style: "flex: 1; min-width: 8em;" },
      }).addEventListener("change", (e) => {
        rule.folder = (e.target as HTMLInputElement).value;
      });
      const up = row.createEl("button", { text: "↑" });
      up.addEventListener("click", () => {
        if (i > 0) { [rules[i - 1], rules[i]] = [rules[i], rules[i - 1]]; this.renderPatternRows(listEl, rules); }
      });
      const del = row.createEl("button", { text: "✕" });
      del.addEventListener("click", () => {
        rules.splice(i, 1);
        this.renderPatternRows(listEl, rules);
      });
    });
  }

  // ------------------------------------------------------------------ local

  private renderLocal(containerEl: HTMLElement, s: typeof this.plugin.settings): void {
    new Setting(containerEl).setName("This device (local)").setHeading();
    new Setting(containerEl).setName("Ollama URL")
      .addText((t) => t.setValue(s.ollamaUrl).onChange(async (v) => {
        s.ollamaUrl = v; await this.plugin.saveSettings();
      }));
    for (const key of ["dreamFolder", "journalFolder", "statsFolder", "inboxFolder"] as const) {
      new Setting(containerEl)
        .setName(labels[key])
        .addText((t) => t.setValue(s[key]).onChange(async (v) => {
          s[key] = v; await this.plugin.saveSettings();
        }));
    }
  }
}
