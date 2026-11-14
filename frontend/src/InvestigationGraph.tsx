import "./InvestigationGraph.css";
import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";

export type GraphNode = {
  id: string;
  kind: string;
  data: { source_id: string; text?: string; url?: string; platform?: string };
};
export type GraphEdge = {
  id: string;
  source_id: string;
  target_id: string;
  action: string;
  timestamp?: string | null;
  inferred?: boolean;
  score?: number;
};
export type Graph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  hidden_nodes: number;
  clusters: { id: string; account_ids: string[]; density: number }[];
};

export function InvestigationGraph({
  graph,
  selected,
  onSelect,
}: {
  graph: Graph;
  selected: string | null;
  onSelect: (node: GraphNode) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const cy = useRef<cytoscape.Core | null>(null);
  useEffect(() => {
    const instance = cytoscape({
      container: container.current,
      elements: [
        ...graph.nodes.map((node) => ({
          data: {
            id: node.id,
            label: node.data.source_id.slice(0, 32),
            kind: node.kind,
          },
        })),
        ...graph.edges.map((edge) => ({
          data: {
            id: edge.id,
            source: edge.source_id,
            target: edge.target_id,
            label: edge.inferred
              ? `coordination ${edge.score?.toFixed(2)}`
              : edge.action,
            inferred: edge.inferred ? 1 : 0,
          },
        })),
      ],
      layout: {
        name: "cose",
        animate: false,
        randomize: false,
        numIter: 300,
        nodeRepulsion: () => 12000,
      },
      minZoom: 0.1,
      maxZoom: 3,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#63dce6",
            label: "data(label)",
            color: "#dde6f3",
            "font-size": 10,
            "text-valign": "bottom",
            "text-margin-y": 8,
            width: 24,
            height: 24,
          },
        },
        {
          selector: 'node[kind="content"]',
          style: { shape: "round-rectangle", "background-color": "#91a7ff" },
        },
        {
          selector: 'node[kind="url"]',
          style: { shape: "diamond", "background-color": "#ecc879" },
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": "#34516b",
            "target-arrow-color": "#34516b",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
          },
        },
        {
          selector: "edge[inferred=1]",
          style: { "line-style": "dashed", "line-color": "#efb370", width: 3 },
        },
        {
          selector: ":selected",
          style: {
            "border-width": 3,
            "border-color": "#fff",
            "background-color": "#fff",
          },
        },
      ],
    });
    instance.on("tap", "node", (event) => {
      const node = graph.nodes.find((n) => n.id === event.target.id());
      if (node) onSelect(node);
    });
    cy.current = instance;
    const observer = new ResizeObserver(() => instance.resize());
    if (container.current) observer.observe(container.current);
    return () => {
      observer.disconnect();
      instance.destroy();
    };
  }, [graph]);
  useEffect(() => {
    cy.current?.nodes().unselect();
    if (selected) cy.current?.getElementById(selected).select();
  }, [selected, graph]);
  return (
    <>
      <div className="toolbar">
        <span className="small muted">
          ● Account · ▰ Content · ◆ URL · dashed = inferred coordination
        </span>
        <button
          className="sample"
          onClick={() => cy.current?.fit(undefined, 35)}
        >
          Fit graph
        </button>
        <button
          className="sample"
          onClick={() => cy.current?.zoom((cy.current?.zoom() || 1) * 1.25)}
        >
          Zoom in
        </button>
        <button
          className="sample"
          onClick={() => cy.current?.zoom((cy.current?.zoom() || 1) / 1.25)}
        >
          Zoom out
        </button>
      </div>
      <div
        ref={container}
        className="investigation-graph"
        role="img"
        aria-label="Interactive account, content and URL relationships. Use the entity selector below for keyboard access."
      />
      <label className="field-label" htmlFor="graph-entity">
        Select an entity (keyboard accessible)
      </label>
      <select
        id="graph-entity"
        value={selected || ""}
        onChange={(e) => {
          const node = graph.nodes.find((n) => n.id === e.target.value);
          if (node) onSelect(node);
        }}
      >
        <option value="">Select entity</option>
        {graph.nodes.map((n) => (
          <option key={n.id} value={n.id}>
            {n.kind}: {n.data.source_id}
          </option>
        ))}
      </select>
    </>
  );
}
