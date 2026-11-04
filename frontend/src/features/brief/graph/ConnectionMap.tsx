import { useMemo, useState } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Button } from "@/components/ui/button";
import {
  pathOf,
  type Graph,
  type GraphNode,
} from "@/features/brief/graph/buildGraph";
import {
  GraphCard,
  HighlightContext,
  type CardData,
} from "@/features/brief/graph/GraphNodes";
import { NodeDetail } from "@/features/brief/graph/NodeDetail";

const nodeTypes = { card: GraphCard };

const COLUMN_TITLE = [
  "Company",
  "What they are doing",
  "Our offerings",
  "Who to talk to",
  "What to say",
];

// The connection map: boxes you can drag, pan and zoom, joined only where the research links
// them. Hover a box to light up its path; select one to read the quote or reasoning behind it.
// A plain list of the same boxes is one click away, for keyboards, screen readers and small
// screens.
export default function ConnectionMap({ graph }: { graph: Graph }) {
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [listView, setListView] = useState(false);

  const lit = useMemo(
    () => (hoverId ? pathOf(hoverId, graph.edges) : null),
    [hoverId, graph.edges],
  );
  const selected: GraphNode | null =
    graph.nodes.find((n) => n.id === selectedId) ?? null;

  // Stable between hovers and clicks, so React Flow keeps the measured size of each box.
  const nodes: Node[] = useMemo(
    () =>
      graph.nodes.map((n) => ({
        id: n.id,
        type: "card",
        position: { x: n.x, y: n.y },
        data: { node: n } satisfies CardData,
      })),
    [graph.nodes],
  );
  const highlight = useMemo(() => ({ lit, selectedId }), [lit, selectedId]);

  const edges: Edge[] = useMemo(
    () =>
      graph.edges.map((e) => {
        const on = lit === null || (lit.has(e.source) && lit.has(e.target));
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          label: e.label ?? undefined,
          animated: lit !== null && on,
          style: {
            strokeDasharray: e.dashed ? "6 5" : undefined,
            strokeWidth: lit !== null && on ? 2.5 : 1.5,
            opacity: on ? 1 : 0.15,
          },
          labelStyle: { fontSize: 11 },
        };
      }),
    [graph.edges, lit],
  );

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          Solid lines are backed by a cited quote. Dashed lines are our
          inference, or something not found yet.
        </p>
        <Button
          size="sm"
          variant="outline"
          aria-pressed={listView}
          onClick={() => setListView((v) => !v)}
        >
          {listView ? "Show the map" : "Show as a list"}
        </Button>
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
        {listView ? (
          <div className="flex flex-col gap-3">
            {COLUMN_TITLE.map((title, column) => {
              const inColumn = graph.nodes.filter((n) => n.column === column);
              if (inColumn.length === 0) return null;
              return (
                <section key={title} aria-label={title}>
                  <h3 className="mb-1 text-xs font-bold uppercase tracking-wide text-muted-foreground">
                    {title}
                  </h3>
                  <ul className="flex flex-col gap-1">
                    {inColumn.map((n) => (
                      <li key={n.id}>
                        <button
                          type="button"
                          onClick={() => setSelectedId(n.id)}
                          aria-pressed={n.id === selectedId}
                          className="w-full rounded-lg border border-border px-3 py-2 text-left text-sm hover:bg-muted aria-pressed:border-primary"
                        >
                          {n.tag ? `${n.tag}: ` : ""}
                          <span className="font-medium">{n.title}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
          </div>
        ) : (
          <div
            className="h-[420px] min-w-0 overflow-hidden rounded-xl border border-border bg-muted/30 sm:h-[480px]"
            role="group"
            aria-label="Connection map"
          >
            <HighlightContext.Provider value={highlight}>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.15 }}
                minZoom={0.3}
                maxZoom={1.6}
                nodesConnectable={false}
                zoomOnScroll={false}
                preventScrolling={false}
                onNodeMouseEnter={(_, node) => setHoverId(node.id)}
                onNodeMouseLeave={() => setHoverId(null)}
                onNodeClick={(_, node) => setSelectedId(node.id)}
                onPaneClick={() => setSelectedId(null)}
                proOptions={{ hideAttribution: true }}
              >
                <Background gap={20} />
                <Controls showInteractive={false} />
              </ReactFlow>
            </HighlightContext.Provider>
          </div>
        )}
        <aside
          aria-live="polite"
          className="rounded-xl border border-border bg-background p-4"
        >
          <NodeDetail node={selected} />
        </aside>
      </div>
    </div>
  );
}
