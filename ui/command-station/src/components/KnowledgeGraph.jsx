import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import * as d3 from 'd3';

const NODE_COLORS = {
  file: "#3B82F6",
  agent: "#7C3AED",
  skill: "#10B981",
  memory: "#F59E0B",
  tool: "#EC4899",
  project: "#06B6D4",
  user_facts: "#F97316"
};

const TYPE_LABELS = {
  file: "File",
  agent: "Agent",
  skill: "Skill",
  memory: "Memory",
  tool: "Tool",
  project: "Project",
  user_facts: "User Fact"
};

const CACHED_COLORS = (type) => NODE_COLORS[type] || "#888888";

function getRadius(d) {
  const count = d.connections?.length || d.connection_count || 0;
  return Math.min(6 + count * 2, 20);
}

function isActive(d) {
  if (!d.last_active) return false;
  return (Date.now() / 1000 - d.last_active) < 60;
}

export default function KnowledgeGraph() {
  const containerRef = useRef();
  const svgRef = useRef();
  const simRef = useRef(null);

  const [data, setData] = useState({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [hoverNode, setHoverNode] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  // Fetch logic
  const fetchData = useCallback(() => {
    fetch("http://localhost:8001/graph")
      .then(res => res.json())
      .then(d => {
        setData(d);
        setLoading(false);
        setError(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
        setError(true);
      });
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    let ws;
    try {
      ws = new WebSocket("ws://localhost:8001/ws");
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === "graph_update") fetchData();
        } catch { }
      };
    } catch { }
    return () => { if (ws) ws.close(); };
  }, [fetchData]);

  // Compute stats
  const stats = useMemo(() => {
    const s = { total: data.nodes.length, active: 0, types: {} };
    data.nodes.forEach(n => {
      if (isActive(n)) s.active++;
      s.types[n.type] = (s.types[n.type] || 0) + 1;
    });
    return s;
  }, [data]);

  const largeGraph = data.nodes.length > 500;

  // D3 Logic
  useEffect(() => {
    if (!svgRef.current || !containerRef.current) return;
    if (data.nodes.length === 0) return;

    const width = containerRef.current.clientWidth || 800;
    const height = containerRef.current.clientHeight || 600;

    const svg = d3.select(svgRef.current);

    // Ensure the main group wrapper exists once
    let g = svg.select("g.graph-container");
    if (g.empty()) {
      g = svg.append("g").attr("class", "graph-container");
      svg.call(d3.zoom().scaleExtent([0.1, 4]).on("zoom", (e) => g.attr("transform", e.transform)));
      svg.on("dblclick.zoom", () => {
        svg.transition().duration(750).call(d3.zoom().transform, d3.zoomIdentity);
      });
    }

    if (!simRef.current) {
      simRef.current = d3.forceSimulation()
        .force("link", d3.forceLink().id(d => d.id).strength(0.3))
        .force("charge", d3.forceManyBody().strength(-120))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .alphaDecay(0.02);
    }

    const sim = simRef.current;

    // Use current nodes/links with the old objects to preserve physics momentum
    const oldNodes = new Map(sim.nodes().map(n => [n.id, n]));
    const newNodes = data.nodes.map(n => {
      const old = oldNodes.get(n.id);
      return old ? Object.assign(old, n) : Object.assign({}, n);
    });

    const newLinks = data.links.map(l => Object.assign({}, l));

    sim.nodes(newNodes);
    sim.force("link").links(newLinks);
    sim.force("collide", d3.forceCollide().radius(d => getRadius(d) + 4));
    sim.alpha(0.3).restart();

    // Data joins
    let linkSelection = g.selectAll("line.link")
      .data(newLinks, d => d.source.id + "-" + d.target.id);

    linkSelection.exit().remove();

    const linkEnter = linkSelection.enter().append("line")
      .attr("class", "link")
      .attr("stroke", "#FFFFFF")
      .attr("stroke-width", d => Math.max(1, (d.strength || 1) * 2));

    linkSelection = linkEnter.merge(linkSelection)
      .attr("stroke-opacity", largeGraph ? 0.05 : 0.15);

    let nodeSelection = g.selectAll("g.node")
      .data(newNodes, d => d.id);

    nodeSelection.exit().remove();

    const nodeEnter = nodeSelection.enter().append("g")
      .attr("class", "node")
      .call(d3.drag()
        .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.1).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
      )
      .on("mouseover", (event, d) => {
        setHoverNode(d);
        setMousePos({ x: event.clientX, y: event.clientY });
      })
      .on("mousemove", (event) => setMousePos({ x: event.clientX, y: event.clientY }))
      .on("mouseout", () => setHoverNode(null))
      .on("click", (event, d) => {
        event.stopPropagation();
        setSelectedNode(d);
      });

    // Add glowing background if active and not large graph
    nodeEnter.append("circle")
      .attr("class", "glow")
      .attr("r", d => getRadius(d) + 3)
      .style("filter", "blur(4px)")
      .style("opacity", 0);

    // Main node circle
    nodeEnter.append("circle")
      .attr("class", "main")
      .attr("r", d => getRadius(d))
      .attr("fill", d => CACHED_COLORS(d.type));

    nodeSelection = nodeEnter.merge(nodeSelection);

    // Update visuals based on state
    nodeSelection.select("circle.main")
      .attr("r", d => getRadius(d))
      .attr("fill", d => CACHED_COLORS(d.type))
      .attr("stroke", d => (selectedNode?.id === d.id) ? "#FFFFFF" : "none")
      .attr("stroke-width", 2);

    if (!largeGraph) {
      nodeSelection.select("circle.glow")
        .attr("fill", d => CACHED_COLORS(d.type))
        .style("opacity", d => isActive(d) ? 0.6 : 0)
        .transition().duration(1000)
        .attr("r", d => isActive(d) ? getRadius(d) + 5 : getRadius(d));
    } else {
      nodeSelection.select("circle.glow").style("opacity", 0);
    }

    sim.on("tick", () => {
      // Direct DOM manipulation via RAF is cleaner, but D3 handles this in RAF implicitly internally
      linkSelection
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);
      nodeSelection
        .attr("transform", d => `translate(${d.x},${d.y})`);
    });

  }, [data, largeGraph, selectedNode]);

  // Handle deselect on background click
  useEffect(() => {
    const handleBg = () => setSelectedNode(null);
    if (svgRef.current) svgRef.current.addEventListener('click', handleBg);
    return () => { if (svgRef.current) svgRef.current.removeEventListener('click', handleBg); };
  }, []);

  if (loading || error || data.nodes.length === 0) {
    return (
      <div style={{ flex: 1, backgroundColor: "#0D0D0D", display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}>
        <div style={{ color: "#7C3AED", fontSize: 16, display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 10, height: 10, background: "#7C3AED", borderRadius: "50%", animation: "pulse 1.5s infinite" }} />
          Knowledge graph unavailable — is Jarvis running?
          <style>{`@keyframes pulse { 0% { opacity: 0.2; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1.2); } 100% { opacity: 0.2; transform: scale(0.8); } }`}</style>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{ position: "relative", flex: 1, backgroundColor: "#0D0D0D", height: "100%", overflow: "hidden" }}>
      <svg ref={svgRef} style={{ width: "100%", height: "100%", display: "block" }} />

      {/* Legend Top-Right */}
      <div style={{ position: "absolute", top: 16, right: selectedNode ? 296 : 16, transition: "right 0.3s", background: "rgba(13,13,13,0.85)", border: "1px solid #1A1A1A", padding: 12, borderRadius: 8, backdropFilter: "blur(4px)", pointerEvents: "none" }}>
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: color }} />
            <span style={{ color: "#A3A3A3", fontSize: 11, fontFamily: "sans-serif" }}>{TYPE_LABELS[type] || type}</span>
          </div>
        ))}
      </div>

      {/* Stats Bar Bottom */}
      <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 36, background: "rgba(13,13,13,0.9)", borderTop: "1px solid #1A1A1A", display: "flex", alignItems: "center", padding: "0 16px", gap: 24, fontSize: 11, color: "#888", fontFamily: "monospace", zIndex: 10 }}>
        <span style={{ color: "#FFF" }}>Total nodes: {stats.total}</span>
        <span style={{ color: stats.active > 0 ? "#7C3AED" : "#888" }}>Active (60s): {stats.active}</span>
        <div style={{ width: 1, height: 14, background: "#333" }} />
        <span>Files: {stats.types["file"] || 0}</span>
        <span>Agents: {stats.types["agent"] || 0}</span>
        <span>Skills: {stats.types["skill"] || 0}</span>
        <span>Memories: {stats.types["memory"] || 0}</span>
        <span>User Facts: {stats.types["user_facts"] || 0}</span>
      </div>

      {/* Detail slide-out panel Right */}
      <div style={{ position: "absolute", top: 0, bottom: 36, right: selectedNode ? 0 : -280, width: 280, background: "rgba(20,20,20,0.95)", borderLeft: "1px solid #262626", transition: "right 0.3s cubic-bezier(0.4, 0, 0.2, 1)", backdropFilter: "blur(8px)", display: "flex", flexDirection: "column", zIndex: 20 }}>
        {selectedNode && (
          <div style={{ padding: 20, flex: 1, overflowY: "auto", fontFamily: "sans-serif", color: "#E5E5E5" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: CACHED_COLORS(selectedNode.type), lineHeight: 1.3 }}>{selectedNode.label || selectedNode.id}</h2>
              <button onClick={() => setSelectedNode(null)} style={{ background: "none", border: "none", color: "#666", cursor: "pointer", fontSize: 16, padding: "0 4px" }}>✕</button>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 16, background: "#1A1A1A", padding: "4px 8px", borderRadius: 4, width: "max-content" }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: CACHED_COLORS(selectedNode.type) }} />
              <span style={{ fontSize: 11, color: "#A3A3A3", textTransform: "uppercase", letterSpacing: 0.5 }}>{TYPE_LABELS[selectedNode.type] || selectedNode.type}</span>
            </div>

            <div style={{ display: "flex", gap: 16, marginBottom: 24 }}>
              <div>
                <div style={{ fontSize: 10, color: "#666", textTransform: "uppercase", marginBottom: 4 }}>Connections</div>
                <div style={{ fontSize: 16, fontWeight: 500 }}>{selectedNode.connections?.length || selectedNode.connection_count || 0}</div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: "#666", textTransform: "uppercase", marginBottom: 4 }}>Last Active</div>
                <div style={{ fontSize: 13, marginTop: 3 }}>
                  {selectedNode.last_active
                    ? ((Date.now() / 1000 - selectedNode.last_active) < 60
                      ? `${Math.floor(Date.now() / 1000 - selectedNode.last_active)} seconds ago`
                      : `${Math.floor((Date.now() / 1000 - selectedNode.last_active) / 60)} minutes ago`)
                    : "Unknown"}
                </div>
              </div>
            </div>

            <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase", marginBottom: 8, letterSpacing: 0.5 }}>Connected To</div>
            <ul style={{ margin: 0, paddingLeft: 16, marginBottom: 24, fontSize: 13, color: "#A3A3A3" }}>
              {data.links.filter(l => l.source.id === selectedNode.id || l.target.id === selectedNode.id).slice(0, 8).map((l, i) => {
                const other = l.source.id === selectedNode.id ? l.target : l.source;
                return <li key={i} style={{ marginBottom: 4 }}>{other.label || other.id}</li>;
              })}
            </ul>

            {selectedNode.metadata && Object.keys(selectedNode.metadata).length > 0 && (
              <>
                <div style={{ fontSize: 11, color: "#666", textTransform: "uppercase", marginBottom: 8, letterSpacing: 0.5 }}>Metadata</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6, background: "#111", padding: 12, borderRadius: 6 }}>
                  {Object.entries(selectedNode.metadata).map(([k, v]) => (
                    <div key={k} style={{ fontSize: 12, wordBreak: "break-word" }}>
                      <span style={{ color: "#737373" }}>{k}:</span> <span style={{ color: "#D4D4D4" }}>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Hover Tooltip */}
      {hoverNode && !selectedNode && (
        <div style={{ position: "fixed", left: mousePos.x + 16, top: mousePos.y + 16, background: "rgba(10,10,10,0.95)", border: "1px solid #333", padding: "10px 14px", borderRadius: 6, pointerEvents: "none", zIndex: 30, color: "#FFF", fontFamily: "sans-serif", width: 220, boxShadow: "0 4px 12px rgba(0,0,0,0.5)" }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: CACHED_COLORS(hoverNode.type), marginBottom: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{hoverNode.label || hoverNode.id}</div>
          <div style={{ fontSize: 11, color: "#888", marginBottom: 8 }}>{TYPE_LABELS[hoverNode.type] || hoverNode.type}</div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
            <span style={{ color: "#666" }}>Connections:</span>
            <span>{hoverNode.connections?.length || hoverNode.connection_count || 0}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginTop: 4 }}>
            <span style={{ color: "#666" }}>Active:</span>
            <span style={{ color: isActive(hoverNode) ? "#10B981" : "#D4D4D4" }}>
              {hoverNode.last_active
                ? ((Date.now() / 1000 - hoverNode.last_active) < 60
                  ? `${Math.floor(Date.now() / 1000 - hoverNode.last_active)}s`
                  : `${Math.floor((Date.now() / 1000 - hoverNode.last_active) / 60)}m`)
                : "-"}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
