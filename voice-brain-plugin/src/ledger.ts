/** Undo ledger — "scratch that" in the plugin. Stored in plugin data; undo refuses
 *  to clobber files edited since (hash check), mirroring the Python ledger. */

import { TFile, type App } from "obsidian";
import type { FileOp, LedgerAction, LedgerData } from "./types";
import { contentHash } from "./util";

export class LedgerError extends Error {}

export class Ledger {
  private data: LedgerData = { actions: [] };
  private loaded = false;

  constructor(private app: App, private depth: number,
              private save: (d: LedgerData) => Promise<void>,
              private load: () => Promise<LedgerData | null>) {}

  private async ensure() {
    if (!this.loaded) {
      this.data = (await this.load()) ?? { actions: [] };
      this.loaded = true;
    }
  }

  /** Record AFTER a successful write. `ops`: [path, priorContent|null] */
  async record(description: string, ops: Array<[string, string | null]>): Promise<void> {
    await this.ensure();
    const built: FileOp[] = await Promise.all(ops.map(async ([p, prior]) => {
      const ab = this.app.vault.getAbstractFileByPath(p);
      const current = ab instanceof TFile ? await this.app.vault.read(ab) : "";
      return { path: p, op: prior === null ? "create" : "modify", prior, afterSha: contentHash(current) };
    }));
    this.data.actions.push({ ts: Date.now(), description, ops: built });
    if (this.data.actions.length > this.depth) this.data.actions = this.data.actions.slice(-this.depth);
    await this.save(this.data);
  }

  last(): LedgerAction | null {
    return this.data.actions[this.data.actions.length - 1] ?? null;
  }

  async undoLast(): Promise<string> {
    await this.ensure();
    const action = this.data.actions.pop();
    if (!action) throw new LedgerError("Nothing to undo.");
    const undone: string[] = [];
    const skipped: string[] = [];
    for (const op of [...action.ops].reverse()) {
      const file = this.app.vault.getAbstractFileByPath(op.path);
      if (!(file instanceof TFile)) {
        skipped.push(`${op.path} (gone)`);
        continue;
      }
      const current = await this.app.vault.read(file);
      if (contentHash(current) !== op.afterSha) {
        skipped.push(`${op.path} (edited since — left alone)`);
        continue;
      }
      if (op.op === "create") {
        await this.app.vault.trash(file, false);
        undone.push(`deleted ${op.path}`);
      } else if (op.prior !== null) {
        await this.app.vault.modify(file, op.prior);
        undone.push(`restored ${op.path}`);
      } else {
        skipped.push(`${op.path} (prior content unrecoverable)`);
      }
    }
    await this.save(this.data);
    return `Undid: ${action.description}.` + (undone.length ? " " + undone.join("; ") : "")
      + (skipped.length ? " Skipped: " + skipped.join("; ") : "");
  }
}
