import { Fragment, type ReactNode } from "react";
import { cn } from "@/lib/utils";

// Renders the Markdown subset the assistant writes (headings, paragraphs, lists, quotes,
// bold, italic, code, http(s) links) as React elements. Never injects HTML, so model output stays inert.

// Underscores mark emphasis only at word boundaries, so identifiers like snake_case stay plain.
const INLINE = /(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|\*\*[^*]+\*\*|(?<!\w)__[^_]+__(?!\w)|`[^`]+`|\*[^*\s][^*]*\*|(?<!\w)_[^_\s][^_]*_(?!\w))/g;

function inline(text: string): ReactNode[] {
  // split() with a capturing group puts the matched markers at odd indices.
  return text.split(INLINE).map((part, i) => {
    if (i % 2 === 0) return part ? <Fragment key={i}>{part}</Fragment> : null;
    const link = /^\[([^\]]+)\]\((.+)\)$/.exec(part);
    if (link) return <a key={i} href={link[2]} target="_blank" rel="noopener noreferrer">{inline(link[1])}<span className="sr-only"> (otwiera się w nowej karcie)</span></a>;
    if ((part.startsWith("**") || part.startsWith("__")) && part.length > 4) return <strong key={i}>{inline(part.slice(2, -2))}</strong>;
    if (part.startsWith("`") && part.length > 2) return <code key={i}>{part.slice(1, -1)}</code>;
    if ((part.startsWith("*") || part.startsWith("_")) && part.length > 2) return <em key={i}>{inline(part.slice(1, -1))}</em>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

type Item = { indent: number; ordered: boolean; text: string };
const ITEM = /^(\s*)([*+-]|\d+[.)])\s+(.*)$/;

function list(items: Item[], key: string): ReactNode {
  const base = items[0].indent;
  const entries: { text: string; children: Item[] }[] = [];
  for (const item of items) {
    if (item.indent > base && entries.length) entries.at(-1)!.children.push(item);
    else entries.push({ text: item.text, children: [] });
  }
  const List = items[0].ordered ? "ol" : "ul";
  return <List key={key}>{entries.map((entry, i) => <li key={i}>{inline(entry.text)}{entry.children.length > 0 && list(entry.children, `${key}-${i}`)}</li>)}</List>;
}

export function Markdown({ text, className }: { text: string; className?: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const heading = /^(#{1,6})\s+(.*?)\s*#*$/.exec(line);
    if (!line.trim() || /^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { i += 1; continue; }
    if (heading) {
      const Heading = heading[1].length === 1 ? "h2" : heading[1].length === 2 ? "h3" : "h4";
      blocks.push(<Heading key={i}>{inline(heading[2])}</Heading>); i += 1; continue;
    }
    if (line.startsWith(">")) {
      const quote: string[] = [];
      while (i < lines.length && lines[i].startsWith(">")) quote.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push(<blockquote key={i}>{inline(quote.join("\n"))}</blockquote>); continue;
    }
    if (ITEM.test(line)) {
      const items: Item[] = [];
      const start = i;
      while (i < lines.length && ITEM.test(lines[i])) {
        const [, indent, marker, body] = ITEM.exec(lines[i])!;
        items.push({ indent: indent.length, ordered: /\d/.test(marker), text: body });
        i += 1;
        // Indented continuation lines belong to the previous item.
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !ITEM.test(lines[i])) items.at(-1)!.text += `\n${lines[i++].trim()}`;
      }
      blocks.push(list(items, `list-${start}`)); continue;
    }
    const paragraph: string[] = [];
    while (i < lines.length && lines[i].trim() && !ITEM.test(lines[i]) && !lines[i].startsWith(">") && !/^#{1,6}\s/.test(lines[i])) paragraph.push(lines[i++]);
    blocks.push(<p key={i}>{inline(paragraph.join("\n"))}</p>);
  }
  return <div className={cn("markdown", className)}>{blocks}</div>;
}
