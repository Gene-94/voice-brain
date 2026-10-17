/** Small pure utilities: frontmatter, slugify, tokens, hashing. */

export function slugify(text: string, maxWords = 8): string {
  const words = text.replace(/[^\w\s-]/g, "").split(/\s+/).filter(Boolean);
  return words.slice(0, maxWords).join("_") || "untitled";
}

export function estTokens(text: string): number {
  return Math.max(1, Math.floor(text.length / 4));
}

export function todayISO(d = new Date()): string {
  return d.toISOString().slice(0, 10);
}

/** Minimal YAML frontmatter parse. Handles our own controlled output well enough. */
export function parseFrontmatter(text: string): { fm: Record<string, any>; body: string } {
  const m = text.match(/\A?^---\s*\n([\s\S]*?)\n---\s*\n?/);
  if (!m) return { fm: {}, body: text };
  const fm: Record<string, any> = {};
  let key = "";
  for (const line of m[1].split("\n")) {
    const kv = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (kv) {
      key = kv[1];
      const raw = kv[2].trim();
      if (raw === "") {
        fm[key] = [];
      } else if (raw === "true" || raw === "false") {
        fm[key] = raw === "true";
      } else if (raw.startsWith("[") && raw.endsWith("]")) {
        fm[key] = raw.slice(1, -1).split(",").map((s) => s.trim().replace(/^['"]|['"]$/g, "")).filter(Boolean);
      } else {
        fm[key] = raw.replace(/^['"]|['"]$/g, "");
      }
    } else if (/^\s+-\s+/.test(line) && key) {
      if (!Array.isArray(fm[key])) fm[key] = [];
      fm[key].push(line.replace(/^\s+-\s+/, "").trim().replace(/^['"]|['"]$/g, ""));
    }
  }
  return { fm, body: text.slice(m[0].length) };
}

/** Serialize frontmatter for our notes (controlled keys only — no yaml dep needed). */
export function serializeFrontmatter(fm: Record<string, any>): string {
  const lines: string[] = ["---"];
  for (const [k, v] of Object.entries(fm)) {
    if (v === null || v === undefined) continue;
    if (Array.isArray(v)) {
      if (v.length === 0) lines.push(`${k}: []`);
      else {
        lines.push(`${k}:`);
        for (const item of v) lines.push(`  - ${item}`);
      }
    } else if (typeof v === "object") {
      lines.push(`${k}: ${JSON.stringify(v)}`);
    } else if (typeof v === "string") {
      lines.push(`${k}: "${v.replace(/"/g, "'")}"`);
    } else {
      lines.push(`${k}: ${v}`);
    }
  }
  lines.push("---", "");
  return lines.join("\n");
}

/** FNV-1a based content hash — undo safety without importing crypto everywhere. */
export function contentHash(text: string): string {
  let h1 = 0x811c9dc5;
  let h2 = 0x01000193;
  for (let i = 0; i < text.length; i++) {
    h1 = ((h1 ^ text.charCodeAt(i)) * 0x01000193) >>> 0;
    h2 = ((h2 + text.charCodeAt(i) * (i + 1)) >>> 0);
  }
  return h1.toString(16).padStart(8, "0") + h2.toString(16).padStart(8, "0");
}

export function uniq<T>(items: T[]): T[] {
  return [...new Set(items)];
}

export function hhmm(ts: number): string {
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function expandTilde(p: string): string {
  const os = require("os") as typeof import("os");
  if (p.startsWith("~/")) return (os as any).homedir() + p.slice(1);
  return p;
}
