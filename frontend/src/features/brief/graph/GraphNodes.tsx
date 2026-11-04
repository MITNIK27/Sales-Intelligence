import { createContext, useContext } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  Briefcase,
  Building2,
  CircleDashed,
  Cpu,
  Ellipsis,
  Handshake,
  MessageSquare,
  Newspaper,
  Package,
  Rocket,
  User,
  type LucideIcon,
} from "lucide-react";

import type { GraphNode } from "@/features/brief/graph/buildGraph";
import { cn } from "@/lib/utils";

const FINDING_ICON: Record<string, LucideIcon> = {
  News: Newspaper,
  Hiring: Briefcase,
  Initiative: Rocket,
  Partnership: Handshake,
  Technology: Cpu,
};

function iconFor(node: GraphNode): LucideIcon {
  switch (node.kind) {
    case "company":
      return Building2;
    case "finding":
      return FINDING_ICON[node.tag ?? ""] ?? Newspaper;
    case "offering":
      return Package;
    case "person":
      return User;
    case "message":
      return MessageSquare;
    case "more":
      return Ellipsis;
    case "gap":
      return CircleDashed;
  }
}

export type CardData = { node: GraphNode };

// Which boxes are lit (the hovered one's path) and which is selected. Kept out of the node objects
// on purpose: giving React Flow new node objects on every hover makes it forget their measured
// size, and the boxes can vanish until it measures them again.
export const HighlightContext = createContext<{
  lit: Set<string> | null;
  selectedId: string | null;
}>({ lit: null, selectedId: null });

// One box on the connection map. The kind is always shown as an icon and a word, never colour
// alone; a dashed border means "not found yet" or "our inference".
export function GraphCard({ data }: NodeProps) {
  const { node } = data as CardData;
  const { lit, selectedId } = useContext(HighlightContext);
  const dim = lit !== null && !lit.has(node.id);
  const selected = node.id === selectedId;
  const Icon = iconFor(node);
  return (
    <div
      className={cn(
        "w-[270px] rounded-xl border bg-background px-3 py-2.5 text-left shadow-sm transition-opacity",
        node.dashed ? "border-dashed" : "border-solid",
        node.emphasis ? "border-primary" : "border-border",
        selected && "ring-2 ring-primary",
        dim && "opacity-25",
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!size-2 !border-0 !bg-muted-foreground"
      />
      <div className="flex items-start gap-2">
        <Icon
          className="mt-0.5 size-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
        <div className="min-w-0">
          {node.tag && (
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {node.tag}
            </p>
          )}
          <p className="break-words text-sm font-semibold leading-snug">
            {node.title}
          </p>
          {node.subtitle && (
            <p className="mt-0.5 line-clamp-2 break-words text-xs text-muted-foreground">
              {node.subtitle}
            </p>
          )}
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!size-2 !border-0 !bg-muted-foreground"
      />
    </div>
  );
}
