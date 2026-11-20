// Turns the plain text the app keeps from a file into something readable: headings, lists, tables
// and links instead of one long run of words. The text itself is never changed; this only decides
// how it is drawn. Nothing here produces HTML, so nothing in a document can run as markup.

export type Block =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "paragraph"; lines: string[] }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "table"; header: string[]; rows: string[][] }
  // A description a model wrote for a picture or table: [IMAGE: ...] or [TABLE: ...].
  | { kind: "ai"; label: "Picture" | "Table"; blocks: Block[] };

export type Inline =
  { kind: "text"; text: string } | { kind: "link"; text: string; href: string };

const HEADING = /^(#{1,6})\s+(.+?)\s*$/;
const BULLET = /^\s*[-•*]\s+(.*)$/;
const NUMBERED = /^\s*\d{1,3}[.)]\s+(.*)$/;
const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|[\s:|-]+\|\s*$/;
const AI_START = /^\[(IMAGE|TABLE):\s?(.*)$/;

function cells(row: string): string[] {
  return row
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split(/(?<!\\)\|/)
    .map((cell) => cell.replace(/\\\|/g, "|").trim());
}

function startsSpecial(line: string): boolean {
  return (
    HEADING.test(line) ||
    BULLET.test(line) ||
    NUMBERED.test(line) ||
    TABLE_ROW.test(line) ||
    AI_START.test(line)
  );
}

export function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }

    const ai = AI_START.exec(line);
    if (ai) {
      // The description runs to the line that closes the bracket (it may contain a table).
      const inner: string[] = [ai[2]];
      let closed = ai[2].trimEnd().endsWith("]");
      i += 1;
      while (!closed && i < lines.length) {
        inner.push(lines[i]);
        closed = lines[i].trimEnd().endsWith("]");
        i += 1;
      }
      const body = inner.join("\n").trimEnd().replace(/\]$/, "");
      blocks.push({
        kind: "ai",
        label: ai[1] === "TABLE" ? "Table" : "Picture",
        blocks: parseBlocks(body),
      });
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({
        kind: "heading",
        level: Math.min(heading[1].length, 3) as 1 | 2 | 3,
        text: heading[2],
      });
      i += 1;
      continue;
    }

    if (TABLE_ROW.test(line)) {
      const rows: string[] = [];
      while (i < lines.length && TABLE_ROW.test(lines[i])) {
        rows.push(lines[i]);
        i += 1;
      }
      if (rows.length >= 2 && TABLE_RULE.test(rows[1])) {
        blocks.push({
          kind: "table",
          header: cells(rows[0]),
          rows: rows.slice(2).map(cells),
        });
      } else {
        blocks.push({ kind: "paragraph", lines: rows.map((r) => r.trim()) });
      }
      continue;
    }

    if (BULLET.test(line) || NUMBERED.test(line)) {
      const ordered = NUMBERED.test(line) && !BULLET.test(line);
      const items: string[] = [];
      while (i < lines.length) {
        const match = ordered ? NUMBERED.exec(lines[i]) : BULLET.exec(lines[i]);
        if (!match) break;
        items.push(match[1]);
        i += 1;
      }
      blocks.push({ kind: "list", ordered, items });
      continue;
    }

    const paragraph: string[] = [];
    while (i < lines.length && lines[i].trim() && !startsSpecial(lines[i])) {
      paragraph.push(lines[i].trim());
      i += 1;
    }
    if (paragraph.length === 0) {
      paragraph.push(line.trim());
      i += 1;
    }
    blocks.push({ kind: "paragraph", lines: paragraph });
  }
  return blocks;
}

// Web addresses and email addresses become links. Punctuation that ends a sentence is not part of
// the address. Only http(s) and mailto are ever produced.
const LINKABLE =
  /(https?:\/\/[^\s<>"]+)|([A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)/g;
const TRAILING = /[.,;:!?)\]}'"”’]+$/;

export function linkify(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const match of text.matchAll(LINKABLE)) {
    const start = match.index ?? 0;
    let found = match[0];
    const trimmed = TRAILING.exec(found)?.[0] ?? "";
    found = trimmed ? found.slice(0, found.length - trimmed.length) : found;
    if (!found) continue;
    if (start > last) out.push({ kind: "text", text: text.slice(last, start) });
    out.push({
      kind: "link",
      text: found,
      href: match[1] ? found : `mailto:${found}`,
    });
    last = start + found.length;
  }
  if (last < text.length) out.push({ kind: "text", text: text.slice(last) });
  return out.length > 0 ? out : [{ kind: "text", text }];
}
