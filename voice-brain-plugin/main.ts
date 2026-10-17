/** Voice Brain — Obsidian plugin entrypoint.
 *
 *  The plugin IS the brain: all vault operations happen here via Obsidian APIs.
 *  Inputs: in-app hotkey capture (getUserMedia+VAD), the Python daemon (global hotkey
 *  transcripts via localhost HTTP), the Android app (audio via HTTP), offline spools.
 *  Everything degrades gracefully; nothing you say is ever lost.
 */

import { Notice, Platform, Plugin, TFile, normalizePath } from "obsidian";
import { Brain, type BrainDeps } from "./src/brain";
import { captureWithVad } from "./src/capture";
import { Ledger } from "./src/ledger";
import { LLMError } from "./src/llm";
import { Ollama } from "./src/llm";
import { Stt, glossaryPrompt } from "./src/stt";
import { DEFAULT_SETTINGS, type LedgerData, type Utterance, type VBSettings } from "./src/types";
import { QueryModal, openStatsQuickView } from "./src/ui/query-modal";
import { DashboardView, VIEW_TYPE_VB_DASHBOARD } from "./src/ui/dashboard";
import { VoiceBrainSettingTab } from "./src/ui/settings-tab";

const STATE_ICONS: Record<string, string> = {
  idle: "🎙️", armed: "🎙️", recording: "🔴", transcribing: "✍️", processing: "🧠",
  dream: "💜", stats: "📊", journal: "📝", note: "🗒️", query: "💬",
  success: "✅", error: "❌", timeout: "⏱️", cancelled: "🚫",
};

export default class VoiceBrainPlugin extends Plugin {
  settings: VBSettings = DEFAULT_SETTINGS;
  brain!: Brain;
  ollama!: Ollama;  // public: settings tab reads the model list from Ollama
  private ledger!: Ledger;
  private stt!: Stt;
  private server: any = null;  // CaptureServer (desktop only; any to avoid a node-module type import)
  private statusBar: HTMLElement | null = null;
  private busy = false;

  async onload(): Promise<void> {
    await this.loadSettings();

    // vault-synced settings (Voice Brain Settings/settings.md) win over
    // local data.json — the plugin follows the same values as phone + daemon
    try {
      const { readSyncedSettings } = await import("./src/settings-file");
      const synced = await readSyncedSettings(this.app);
      if (synced.quick_model) this.settings.modelQuick = synced.quick_model;
      if (synced.deep_model) this.settings.modelDeep = synced.deep_model;
      if (synced.stt_language) this.settings.language = synced.stt_language;
      if (synced.stt_model) this.settings.whisperModel = synced.stt_model;
    } catch (e) {
      console.warn(`[voice-brain] synced settings unavailable: ${e}`);
    }

    this.ollama = new Ollama(this.settings);
    this.stt = new Stt(this.settings);
    this.ledger = new Ledger(this.app, this.settings.undoDepth,
      async (d: LedgerData) => { await this.saveData({ vbLedger: d, vbSettings: this.settings }); },
      async () => ((await this.loadData()) as any)?.vbLedger ?? null);
    this.brain = new Brain(this.deps());

    // status bar
    this.statusBar = this.addStatusBarItem();
    this.statusBar.addClass("vb-statusbar");
    this.statusBar.setText("🎙️");
    if (Platform.isDesktopApp) {
      this.statusBar.onclick = () => void this.capture();
      // ribbon + mic capture: desktop only (mobile captures through the phone app)
      this.addRibbonIcon("mic", "Voice Brain capture", () => void this.capture());
    }

    // commands
    if (Platform.isDesktopApp) {
      this.addCommand({ id: "capture", name: "Capture (arm, speak, auto-stop)",
                       hotkeys: [{ modifiers: ["Mod", "Shift"], key: "v" }],
                       callback: () => void this.capture() });
    }
    this.addCommand({ id: "ask", name: "Ask my brain",
                     callback: () => new QueryModal(this.app, this).open() });
    this.addCommand({ id: "generate-stats", name: "Generate today's stats",
                     callback: () => void this.runStats() });
    this.addCommand({ id: "brief", name: "Brief me", callback: () => void this.brief() });
    this.addCommand({ id: "undo", name: "Undo last Voice Brain action",
                     callback: () => void this.undo() });
    this.addCommand({ id: "yesterday", name: "Yesterday's stats (quick view)",
                     callback: () => openStatsQuickView(this.app, this) });

    this.registerView(VIEW_TYPE_VB_DASHBOARD, (leaf) => new DashboardView(leaf, this));
    this.addCommand({ id: "dashboard", name: "Open dashboard",
                     callback: () => void this.openDashboard() });

    this.addSettingTab(new VoiceBrainSettingTab(this.app, this));

    this.app.workspace.onLayoutReady(async () => {
      this.ensureFolders();
      if (Platform.isDesktopApp) {
        // server (daemon relay + phone audio) and offline ingest need Node — desktop only
        const { CaptureServer, ingestCaptureFolders, ingestPending } = await import("./src/server");
        this.applyServerSetting(CaptureServer);
        await this.ingestOffline(ingestPending, ingestCaptureFolders);
        this.registerInterval(window.setInterval(() => void this.ingestOffline(ingestPending, ingestCaptureFolders), 60_000));
      }
    });
  }

  onunload(): void {
    this.server?.stop();
  }

  deps(): BrainDeps {
    return { app: this.app, settings: this.settings, ollama: this.ollama,
             ledger: this.ledger, stt: this.stt };
  }

  // ------------------------------------------------------------------ settings

  async loadSettings(): Promise<void> {
    const data = (await this.loadData()) ?? {};
    const saved = (data as any).vbSettings ?? {};
    this.settings = Object.assign({}, DEFAULT_SETTINGS, saved);
  }

  async saveSettings(): Promise<void> {
    const ledgerData = ((await this.loadData()) as any)?.vbLedger ?? { actions: [] };
    await this.saveData({ vbSettings: this.settings, vbLedger: ledgerData });
  }

  // ------------------------------------------------------------------ status

  private setState(state: string, title = ""): void {
    if (!this.statusBar) return;
    this.statusBar.setText(STATE_ICONS[state] ?? "🎙️");
    this.statusBar.setAttribute("aria-label", title || state);
  }

  // ------------------------------------------------------------------ folder bootstrap

  ensureFolders(): void {
    for (const folder of [this.settings.dreamFolder, this.settings.journalFolder,
                          this.settings.statsFolder, this.settings.inboxFolder]) {
      const p = normalizePath(folder);
      if (!this.app.vault.getAbstractFileByPath(p)) {
        void this.app.vault.createFolder(p).catch(() => { /* races are fine */ });
      }
    }
  }

  // ------------------------------------------------------------------ capture (in-app)

  async capture(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    try {
      const result = await captureWithVad(this.settings, (state, level) => {
        this.setState(state);
        if (this.statusBar) {
          this.statusBar.style.opacity = state === "recording"
            ? String(0.5 + level / 2) : "1";
        }
      });
      if (result.state === "timeout" || !result.blob) {
        this.setState("timeout"); this.flash("⏱️ Nothing heard");
        return;
      }
      this.setState("transcribing");
      const glossary = glossaryPrompt(this.settings, this.app);
      const tr = await this.stt.transcribeBlob(
        new Uint8Array(await result.blob.arrayBuffer()), "capture.webm", glossary || undefined);
      if (!tr.text) {
        this.setState("timeout"); this.flash("❓ Didn't catch that — try again");
        return;
      }
      await this.processUtterance({ text: tr.text, source: "in-app", ts: Date.now(),
                                    confidence: tr.avgLogprob });
    } catch (e: any) {
      this.setState("error");
      new Notice(`Voice Brain: ${String(e?.message ?? e)}`);
    } finally {
      this.busy = false;
    }
  }

  /** Shared path for all utterances (in-app, daemon, phone, spool). */
  async processUtterance(u: { text: string; source: Utterance["source"]; ts: number; confidence?: number | null }):
      Promise<string> {
    this.setState("processing");
    const res = await this.brain.routeUtterance(u);
    this.setState(res.state);
    this.brain.lastResult = res.title;
    new Notice(res.title, 6000);
    if (res.body) new Notice(res.body, 8000);
    setTimeout(() => this.setState("idle"), 4000);
    // dictation mode: keep the mic metaphor alive by hinting continued availability
    if (this.brain.dictation.active) this.setState("armed");
    return `${res.title}\n${res.body}`;
  }

  private flash(text: string): void {
    new Notice(text, 4000);
    setTimeout(() => this.setState("idle"), 3000);
  }

  // ------------------------------------------------------------------ commands

  private async runStats(): Promise<void> {
    this.setState("processing");
    try {
      const { handleStats } = await import("./src/routes/stats");
      const res = await handleStats(this.deps(), Date.now());
      new Notice(res.title, 6000);
      if (res.body) new Notice(res.body, 8000);
    } catch (e: any) {
      new Notice(`❌ Stats failed: ${String(e?.message ?? e)}`);
    } finally {
      this.setState("idle");
    }
  }

  private async brief(): Promise<void> {
    new Notice("🌅 Briefing…");
    new Notice(await this.brain.brief(), 15000);
  }

  private async undo(): Promise<void> {
    try {
      new Notice(await this.ledger.undoLast());
    } catch (e: any) {
      new Notice(`❌ ${String(e?.message ?? e)}`);
    }
  }

  private async openDashboard(): Promise<void> {
    const existing = this.app.workspace.getLeavesOfType(VIEW_TYPE_VB_DASHBOARD);
    const leaf = existing[0] ?? this.app.workspace.getRightLeaf(false)!;
    await leaf.setViewState({ type: VIEW_TYPE_VB_DASHBOARD, active: true });
    this.app.workspace.revealLeaf(leaf);
  }

  // ------------------------------------------------------------------ server (daemon + phone)

  applyServerSetting(CS?: typeof import("./src/server").CaptureServer): void {
    this.server?.stop();
    this.server = null;
    if (!this.settings.serverEnabled) return;
    const CaptureServer = CS ?? require("./src/server").CaptureServer;
    this.server = new (CaptureServer as any)(
      this.settings.serverPort,
      this.settings.serverBindHost,
      this.settings.serverToken,
      async (u: Utterance) => this.processUtterance(u),      // pre-transcribed text (daemon)
      async (bytes: Uint8Array, filename: string) => {   // raw audio (Android app)
        const glossary = glossaryPrompt(this.settings, this.app);
        const tr = await this.stt.transcribeBlob(bytes, filename, glossary || undefined);
        if (!tr.text) return "❓ Empty capture";
        return this.processUtterance({ text: tr.text, source: "phone",
                                       ts: Date.now(), confidence: tr.avgLogprob });
      },
    );
    try {
      this.server.start();
      console.log(`[voice-brain] capture server on ${this.settings.serverBindHost}:${this.settings.serverPort}`);
    } catch (e: any) {
      new Notice(`Voice Brain capture server failed to start: ${String(e?.message ?? e)}`);
    }
  }

  // ------------------------------------------------------------------ offline ingest

  private async ingestOffline(ingestPending?: typeof import("./src/server").ingestPending,
                             ingestCaptureFolders?: typeof import("./src/server").ingestCaptureFolders): Promise<void> {
    if (!ingestPending || !ingestCaptureFolders) return;
    try {
      const n1 = await ingestPending(this.settings.pendingFile,
        async (u) => this.processUtterance({ ...u, source: "spool" }));
      const n2 = await ingestCaptureFolders(this.settings.captureFolders,
        async (bytes, filename) => {
          const glossary = glossaryPrompt(this.settings, this.app);
          const tr = await this.stt.transcribeBlob(bytes, filename, glossary || undefined);
          if (!tr.text) return "❓ Empty capture";
          return this.processUtterance({ text: tr.text, source: "syncthing", ts: Date.now() });
        },
        (msg) => console.warn(`[voice-brain] ${msg}`));
      if (n1 + n2 > 0) new Notice(`📥 Ingested ${n1 + n2} offline capture(s)`);
    } catch (e: any) {
      console.warn(`[voice-brain] offline ingest failed: ${e?.message ?? e}`);
    }
  }
}
