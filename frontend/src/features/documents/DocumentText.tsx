import { Sparkles } from "lucide-react";
import { Fragment } from "react";

import {
  linkify,
  parseBlocks,
  type Block,
} from "@/features/documents/textBlocks";
import { cn } from "@/lib/utils";

// The text kept from a file, drawn the way it reads: headings, paragraphs that keep their lines,
// lists, tables, working links, and a clearly marked box around anything a model wrote.
export function DocumentText({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  return (
    <div
      className={cn("flex flex-col gap-3 text-sm leading-relaxed", className)}
    >
      {parseBlocks(text).map((block, index) => (
        <BlockView key={index} block={block} />
      ))}
    </div>
  );
}

function Inline({ text }: { text: string }) {
  return (
    <>
      {linkify(text).map((part, index) =>
        part.kind === "link" ? (
          <a
            key={index}
            href={part.href}
            target="_blank"
            rel="noopener noreferrer"
            className="break-all text-primary-text underline underline-offset-2 hover:text-primary"
          >
            {part.text}
          </a>
        ) : (
          <Fragment key={index}>{part.text}</Fragment>
        ),
      )}
    </>
  );
}

function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case "heading":
      return (
        <p
          role="heading"
          aria-level={block.level + 3}
          className={cn(
            "font-bold",
            block.level === 1
              ? "text-lg"
              : block.level === 2
                ? "text-base"
                : "text-sm",
          )}
        >
          <Inline text={block.text} />
        </p>
      );
    case "paragraph":
      return (
        <p className="break-words">
          {block.lines.map((line, index) => (
            <Fragment key={index}>
              {index > 0 && <br />}
              <Inline text={line} />
            </Fragment>
          ))}
        </p>
      );
    case "list": {
      const Tag = block.ordered ? "ol" : "ul";
      return (
        <Tag
          className={cn(
            "flex flex-col gap-1 pl-6",
            block.ordered ? "list-decimal" : "list-disc",
          )}
        >
          {block.items.map((item, index) => (
            <li key={index} className="break-words">
              <Inline text={item} />
            </li>
          ))}
        </Tag>
      );
    }
    case "table":
      return (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr>
                {block.header.map((cell, index) => (
                  <th
                    key={index}
                    className="border border-border bg-muted px-2 py-1 font-semibold"
                  >
                    <Inline text={cell} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => (
                    <td
                      key={c}
                      className="border border-border px-2 py-1 align-top"
                    >
                      <Inline text={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "ai":
      return (
        <div className="border-l-4 border-l-chip-warning-fg bg-chip-warning-bg/40 p-3">
          <p className="mb-1 flex items-center gap-1 text-xs font-semibold text-chip-warning-fg">
            <Sparkles className="size-3.5" aria-hidden="true" />
            {block.label} described by AI, not written by the author
          </p>
          <div className="flex flex-col gap-2">
            {block.blocks.map((inner, index) => (
              <BlockView key={index} block={inner} />
            ))}
          </div>
        </div>
      );
  }
}
