/** Ollama client — same discipline as the Python side:
 *  explicit num_ctx on every call (silent truncation is the worst failure mode),
 *  JSON mode + one repair retry, keep_alive residency. */

import type { VBSettings } from "./types";
import { estTokens } from "./util";

export class ContextTooLarge extends Error {}
export class LLMError extends Error {}

type Validator = (doc: any) => string[];

export interface Lane {
  model: string;
  temperature: number;
}

// built from concatenated parts so no literal tags appear in source
const THINK_RE = new RegExp("<" + "think" + ">[\\s\\S]*?</" + "think" + ">", "g");
const FENCE_RE = /```(?:json)?\s*([\s\S]*?)```/;

export class Ollama {
  constructor(private s: VBSettings) {}

  lane(which: "quick" | "deep"): Lane {
    return which === "quick"
      ? { model: this.s.modelQuick, temperature: this.s.temperatureQuick }
      : { model: this.s.modelDeep, temperature: this.s.temperatureDeep };
  }

  private numCtxFor(prompt: string, system?: string): number {
    const est = estTokens(prompt) + estTokens(system ?? "") + 512;
    const want = Math.max(4096, est * 2);
    if (want > this.s.maxNumCtx) {
      throw new ContextTooLarge(
        `Prompt needs ~${est} tokens (num_ctx ${want} > max ${this.s.maxNumCtx}). ` +
        `Refusing to send: silent truncation is worse than a loud error.`);
    }
    return want;
  }

  private stripThinking(text: string): string {
    return text.replace(THINK_RE, "").trim();
  }

  async generate(prompt: string, opts: {
    lane?: "quick" | "deep";
    system?: string;
    json?: boolean;
    validator?: Validator;
  } = {}): Promise<any> {
    const ln = this.lane(opts.lane ?? "quick");
    const payload: Record<string, any> = {
      model: ln.model,
      prompt,
      stream: false,
      keep_alive: this.s.keepAlive,
      options: { temperature: ln.temperature, num_ctx: this.numCtxFor(prompt, opts.system) },
    };
    if (opts.system) payload.system = opts.system;
    if (opts.json) payload.format = "json";

    let candidate = await this.post(payload);
    if (!opts.json) return candidate;

    // JSON mode: parse (strip reasoning blocks / fences) + one repair retry
    for (let attempt = 0; attempt < 2; attempt++) {
      const cleaned = this.stripThinking(candidate);
      const fence = cleaned.match(FENCE_RE);
      const raw = fence ? fence[1].trim() : cleaned;
      let doc: any;
      let errors: string[] = [];
      try {
        doc = JSON.parse(raw);
      } catch (e: any) {
        errors = [`invalid JSON: ${e.message}`];
      }
      if (errors.length === 0 && opts.validator) errors = opts.validator(doc) ?? [];
      if (errors.length === 0) return doc;

      if (attempt === 0) {
        const repair = {
          ...payload,
          prompt: `${payload.prompt}\n\n---\nYour previous reply was NOT acceptable:\n` +
            errors.map((e) => `- ${e}`).join("\n") +
            `\nReturn the corrected JSON document ONLY. No prose, no fences.`,
        };
        candidate = await this.post(repair);
      } else {
        throw new LLMError(`JSON validation failed after repair: ${errors.join("; ")}`);
      }
    }
    throw new LLMError("unreachable");
  }

  private async post(payload: Record<string, any>): Promise<string> {
    const resp = await fetch(`${this.s.ollamaUrl}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      throw new LLMError(`Ollama ${resp.status}: ${(await resp.text()).slice(0, 300)}`);
    }
    const data = await resp.json();
    const text = String(data.response ?? "").trim();
    if (!text) throw new LLMError("Ollama returned an empty response");
    return text;
  }

  async listModels(): Promise<string[]> {
    try {
      const resp = await fetch(`${this.s.ollamaUrl}/api/tags`);
      if (!resp.ok) return [];
      const data = await resp.json();
      return (data.models ?? []).map((m: any) => m.name as string);
    } catch {
      return [];
    }
  }
}
