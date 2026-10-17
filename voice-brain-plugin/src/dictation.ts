/** Continuous dictation state — the server keeps accepting utterances while active. */

export class DictationState {
  active = false;
  startedAt: number | null = null;

  start(): void {
    this.active = true;
    this.startedAt = Date.now();
  }

  stop(): void {
    this.active = false;
    this.startedAt = null;
  }
}
