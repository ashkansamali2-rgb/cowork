import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";

const NODE_COLORS = {
  file: "#4A90D9",
  agent: "#7C3AED",
  skill: "#22C55E",
  memory: "#F59E0B",
  tool: "#EC4899",
  project: "#06B6D4",
};

const TYPE_LABELS = {
  file: "File",
  agent: "Agent",
  skill: "Skill",
  memory: "Memory",
  tool: "Tool",
  project: "Project",
};

function NodeRadiusByConnections(d) {
  const base = 7;
  const count = d.connection_count || d.connections || 0;
  return Math.min(base + Math.sqrt(count) * 2.5, 28);
}

function isRecentlyActive(node) {
  if (!node.last_active) return false;
  return (Date.now() / 1000 - node.last_active) < 60;
}

export default function KnowledgeGraph() {
  const svgRef = useRef(null);
  const simRef = useRef(null);
  const [graphData, setGraphData] = useState({ nodes: [], edges: [], stats: {} });
  const [selected, setSelected] = useState(null);
  const [tooltip, setTooltip] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchGraph = useCallback(() => {
    fetch("http://localhost:8001/graph")
      .then((r) => r.json())
      .then((data) => {
        setGraphData(data);
        setLoading(false);
        setError(null);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  // Initial load + 30s polling
  useEffect(() => {
    fetchGraph();
    const interval = setInterval(fetchGraph, 30000);
    return () => clearInterval(interval);
  }, [fetchGraph]);

  // WebSocket for live graph_update events
  useEffect(() => {
    let ws;
    try {
      ws = new WebSocket("ws://localhost:8001/ws");
      ws.onopen = () => {
        ws.send(JSON.stringify({ register: "graph_viewer", client: "graph" }));
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "graph_update") {
            fetchGraph();
          }
        } catch {}
      };
    } catch {}
    return () => { try { ws && ws.close(); } catch {} };
  }, [fetchGraph]);

  // D3 force simulation
  useEffect(() => {
    if (!graphData.nodes.length || !svgRef.current) return;

    if (simRef.current) {
      simRef.current.stop();
    }

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = svgRef.current.clientWidth || 900;
    const height = svgRef.current.clientHeight || 650;

    const nodes = graphData.nodes.map((d) => ({ ...d }));
    const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));

    const edges = graphData.edges
      .map((e) => ({
        source: nodeById[e.from] || e.from,
        target: nodeById[e.to] || e.to,
        rel: e.rel,
      }))
      .filter((e) => e.source && e.target);

    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(edges).id((d) => d.id).distance(90))
      .force("charge", d3.forceManyBody().strength(-220))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius((d) => NodeRadiusByConnections(d) + 6));

    simRef.current = sim;

    const g = svg.append("g");
    svg.call(d3.zoom().scaleExtent([0.1, 4]).on("zoom", (e) => g.attr("transform", e.transform)));

    // Edges
    const link = g.append("g").selectAll("line")
      .data(edges).enter().append("line")
      .attr("stroke", "rgba(255,255,255,0.12)")
      .attr("stroke-width", 1);

    // Node groups
    const nodeGroup = g.append("g").selectAll("g.node")
      .data(nodes).enter()
      .append("g")
      .attr("class", "node")
      .attr("cursor", "pointer")
      .on("mouseover", (event, d) => {
        setTooltip({ x: event.clientX, y: event.clientY, node: d });
      })
      .on("mousemove", (event) => {
        setTooltip((prev) => prev ? { ...prev, x: event.clientX, y: event.clientY } : prev);
      })
      .on("mouseout", () => setTooltip(null))
      .on("click", (_, d) => {
        setSelected(d);
        fetch(`http://localhost:8001/graph/touch/${encodeURIComponent(d.id)}`, { method: "POST" }).catch(() => {});
      })
      .call(d3.drag()
        .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));

    // Pulse rings for recently active nodes
    nodeGroup.filter((d) => isRecentlyActive(d))
      .append("circle")
      .attr("class", "pulse-ring")
      .attr("r", (d) => NodeRadiusByConnections(d) + 4)
      .attr("fill", "none")
      .attr("stroke", (d) => NODE_COLORS[d.type] || "#6b7280")
      .attr("stroke-width", 1.5)
      .attr("opacity", 0.5)
      .append("animate")
      .attr("attributeName", "r")
      .attr("from", (d) => NodeRadiusByConnections(d) + 4)
      .attr("to", (d) => NodeRadiusByConnections(d) + 14)
      .attr("dur", "2s")
      .attr("repeatCount", "indefinite");

    nodeGroup.filter((d) => isRecentlyActive(d))
      .select("animate")
      .attr("attributeName", "opacity")
      .attr("from", "0.5")
      .attr("to", "0")
      .attr("dur", "2s")
      .attr("repeatCount", "indefinite");

    // Main circles
    nodeGroup.append("circle")
      .attr("r", (d) => NodeRadiusByConnections(d))
      .attr("fill", (d) => NODE_COLORS[d.type] || "#6b7280")
      .attr("stroke", (d) => isRecentlyActive(d) ? "#ffffff" : "rgba(255,255,255,0.15)")
      .attr("stroke-width", (d) => isRecentlyActive(d) ? 2 : 1);

    // Labels
    nodeGroup.append("text")
      .text((d) => {
        const label = d.label || d.id;
        return label.length > 18 ? label.slice(0, 16) + ".." : label;
      })
      .attr("font-size", 9)
      .attr("fill", "rgba(255,255,255,0.6)")
      .attr("dx", (d) => NodeRadiusByConnections(d) + 4)
      .attr("dy", 3)
      .attr("pointer-events", "none");

    sim.on("tick", () => {
      link
        .attr("x1", (d) => d.source.x)
        .attr("y1", (d) => d.source.y)
        .attr("x2", (d) => d.target.x)
        .attr("y2", (d) => d.target.y);
      nodeGroup.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    return () => sim.stop();
  }, [graphData]);

  const stats = graphData.stats || {};
  const nodeTypes = stats.node_types || {};

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", background: "#0A0A12", color: "#6b7280" }}>
      Loading graph...
    </div>
  );

  if (error) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", background: "#0A0A12", color: "#EC4899" }}>
      Graph unavailable: {error}
    </div>
  );

  return (
    <div style={{ display: "flex", height: "100%", background: "#0A0A12", position: "relative" }}>
      <svg ref={svgRef} style={{ flex: 1, width: "100%", height: "100%" }} />

      {/* Stats panel top-right */}
      <div style={{
        position: "absolute", top: 12, right: selected ? 256 : 12,
        background: "rgba(15,15,25,0.88)", border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 8, padding: "10px 14px", minWidth: 180,
        backdropFilter: "blur(8px)", transition: "right 0.2s",
      }}>
        <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 10, marginBottom: 8, letterSpacing: "0.08em", textTransform: "uppercase" }}>Graph Stats</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <StatRow label="Total nodes" value={stats.total_nodes || 0} />
          <StatRow label="Total edges" value={stats.total_edges || 0} />
          {stats.most_connected && <StatRow label="Most connected" value={stats.most_connected} />}
          {Object.entries(nodeTypes).map(([type, count]) => (
            <StatRow key={type} label={TYPE_LABELS[type] || type} value={count} color={NODE_COLORS[type]} />
          ))}
        </div>
      </div>

      {/* Node legend top-left */}
      <div style={{
        position: "absolute", top: 12, left: 12,
        background: "rgba(15,15,25,0.75)", border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 8, padding: "8px 12px",
      }}>
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
            <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 10 }}>{TYPE_LABELS[type]}</span>
          </div>
        ))}
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div style={{
          position: "fixed", left: tooltip.x + 12, top: tooltip.y - 8,
          background: "rgba(15,15,25,0.95)", border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 6, padding: "6px 10px", pointerEvents: "none", zIndex: 1000,
        }}>
          <div style={{ color: "#f9fafb", fontSize: 12, fontWeight: 600 }}>{tooltip.node.label || tooltip.node.id}</div>
          <div style={{ color: NODE_COLORS[tooltip.node.type] || "#9ca3af", fontSize: 10, marginTop: 2 }}>
            {TYPE_LABELS[tooltip.node.type] || tooltip.node.type}
          </div>
          <div style={{ color: "rgba(255,255,255,0.35)", fontSize: 10, marginTop: 2 }}>
            {tooltip.node.connection_count || 0} connections
            {isRecentlyActive(tooltip.node) && <span style={{ color: "#22C55E", marginLeft: 6 }}>active</span>}
          </div>
        </div>
      )}

      {/* Detail panel */}
      {selected && (
        <div style={{
          width: 240, padding: 16, background: "rgba(15,15,25,0.95)",
          borderLeft: "1px solid rgba(255,255,255,0.08)", overflowY: "auto",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
            <div style={{ color: "#f9fafb", fontWeight: 600, fontSize: 13, wordBreak: "break-word", flex: 1 }}>
              {selected.label || selected.id}
            </div>
            <button
              onClick={() => setSelected(null)}
              style={{ color: "#6b7280", background: "none", border: "none", cursor: "pointer", fontSize: 16, marginLeft: 8 }}
            >x</button>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: NODE_COLORS[selected.type] || "#6b7280" }} />
            <span style={{ color: NODE_COLORS[selected.type] || "#6b7280", fontSize: 11 }}>
              {TYPE_LABELS[selected.type] || selected.type}
            </span>
          </div>
          <div style={{ color: "#9ca3af", fontSize: 11, marginBottom: 6 }}>
            {selected.connection_count || 0} connections
          </div>
          {selected.last_active && (
            <div style={{ color: "rgba(255,255,255,0.3)", fontSize: 10, marginBottom: 10 }}>
              Last active: {new Date(selected.last_active * 1000).toLocaleString()}
            </div>
          )}
          {selected.properties && Object.keys(selected.properties).length > 0 && (
            <div>
              <div style={{ color: "rgba(255,255,255,0.25)", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Properties</div>
              {Object.entries(selected.properties).map(([k, v]) => (
                <div key={k} style={{ color: "#9ca3af", fontSize: 10, marginBottom: 3, wordBreak: "break-all" }}>
                  <span style={{ color: "rgba(255,255,255,0.35)" }}>{k}:</span> {String(v)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatRow({ label, value, color }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
      <span style={{ color: "rgba(255,255,255,0.35)", fontSize: 10 }}>{label}</span>
      <span style={{ color: color || "rgba(255,255,255,0.7)", fontSize: 11, fontWeight: 600 }}>{value}</span>
    </div>
  );
}
