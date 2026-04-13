import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";

const NODE_COLORS = {
  file: "#3b82f6",
  agent: "#8b5cf6",
  skill: "#10b981",
  memory: "#f59e0b",
  tool: "#ef4444",
  project: "#06b6d4",
};

export default function KnowledgeGraph() {
  const svgRef = useRef(null);
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("http://localhost:8001/graph")
      .then((r) => r.json())
      .then((data) => { setGraphData(data); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, []);

  useEffect(() => {
    if (!graphData.nodes.length || !svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;

    const sim = d3.forceSimulation(graphData.nodes)
      .force("link", d3.forceLink(graphData.edges).id((d) => d.id).distance(80))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2));

    const g = svg.append("g");

    svg.call(d3.zoom().on("zoom", (e) => g.attr("transform", e.transform)));

    const link = g.append("g").selectAll("line")
      .data(graphData.edges).enter().append("line")
      .attr("stroke", "#374151").attr("stroke-width", 1.5);

    const node = g.append("g").selectAll("circle")
      .data(graphData.nodes).enter().append("circle")
      .attr("r", (d) => d.type === "project" ? 14 : 9)
      .attr("fill", (d) => NODE_COLORS[d.type] || "#6b7280")
      .attr("cursor", "pointer")
      .on("click", (_, d) => {
        setSelected(d);
        fetch(`http://localhost:8001/graph/touch/${d.id}`, { method: "POST" });
      })
      .call(d3.drag()
        .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));

    const label = g.append("g").selectAll("text")
      .data(graphData.nodes).enter().append("text")
      .text((d) => d.label || d.id)
      .attr("font-size", 10).attr("fill", "#9ca3af").attr("dx", 12).attr("dy", 4);

    sim.on("tick", () => {
      link.attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y)
          .attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
      node.attr("cx", (d) => d.x).attr("cy", (d) => d.y);
      label.attr("x", (d) => d.x).attr("y", (d) => d.y);
    });

    return () => sim.stop();
  }, [graphData]);

  if (loading) return <div style={{ padding: 32, color: "#9ca3af" }}>Loading graph...</div>;
  if (error) return <div style={{ padding: 32, color: "#ef4444" }}>Error: {error}</div>;

  return (
    <div style={{ display: "flex", height: "100%", background: "#111827" }}>
      <svg ref={svgRef} style={{ flex: 1, width: "100%", height: "100%" }} />
      {selected && (
        <div style={{ width: 240, padding: 16, background: "#1f2937", borderLeft: "1px solid #374151" }}>
          <div style={{ color: "#f9fafb", fontWeight: 600, marginBottom: 8 }}>{selected.label || selected.id}</div>
          <div style={{ color: "#6b7280", fontSize: 12, marginBottom: 4 }}>Type: {selected.type}</div>
          <div style={{ color: "#6b7280", fontSize: 12 }}>Connections: {selected.connections || 0}</div>
          {selected.metadata && Object.entries(selected.metadata).map(([k, v]) => (
            <div key={k} style={{ color: "#9ca3af", fontSize: 11, marginTop: 4 }}>{k}: {String(v)}</div>
          ))}
        </div>
      )}
    </div>
  );
}
