import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import * as d3 from 'd3';

const NODE_COLORS = {
  file: "#3B82F6",
  agent: "#A855F7",
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

const colorOf = (type) => NODE_COLORS[type] || "#555";

// Organic radius — agents and tools are bigger, files are tiny neurons
function neuronRadius(d) {
  if (d.type === "agent") return 10;
  if (d.type === "tool") return 7;
  const cc = d.connection_count || 0;
  return Math.max(2.5, Math.min(3 + cc * 0.5, 8));
}

export default function KnowledgeGraph() {
  const containerRef = useRef();
  const svgRef = useRef();
  const simRef = useRef(null);

  const [rawData, setRawData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [hoverNode, setHoverNode] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  const fetchData = useCallback(() => {
    fetch("http://localhost:8001/graph")
      .then(res => res.json())
      .then(d => {
        setRawData(d);
        setLoading(false);
        setError(false);
      })
      .catch(() => {
        setLoading(false);
        setError(true);
      });
  }, []);

  useEffect(() => {
    fetchData();
    const iv = setInterval(fetchData, 30000);
    return () => clearInterval(iv);
  }, [fetchData]);

  // Build the organic spider graph data: create edges from folder hierarchy
  const data = useMemo(() => {
    if (!rawData) return { nodes: [], links: [] };
    const nodes = rawData.nodes || [];
    const backendLinks = rawData.links || rawData.edges || [];

    // Build folder-based links: files in the same directory get connected through a virtual folder node
    const folderMap = {};
    const folderNodes = [];
    const syntheticLinks = [];

    nodes.forEach(n => {
      if (n.type === "file" && n.id.includes("/")) {
        const parts = n.id.split("/");
        const folder = parts.slice(0, -1).join("/");
        if (!folderMap[folder]) {
          folderMap[folder] = {
            id: `__folder__${folder}`,
            label: parts[parts.length - 2] || folder,
            type: "project",
            properties: {},
            connection_count: 0,
            last_active: n.last_active
          };
          folderNodes.push(folderMap[folder]);
        }
        folderMap[folder].connection_count++;
        syntheticLinks.push({
          source: n.id,
          target: `__folder__${folder}`,
          strength: 0.4
        });
      }
    });

    // Connect folder nodes to parent folders for hierarchy
    Object.keys(folderMap).forEach(folder => {
      const parts = folder.split("/");
      if (parts.length > 1) {
        const parent = parts.slice(0, -1).join("/");
        if (folderMap[parent]) {
          syntheticLinks.push({
            source: `__folder__${folder}`,
            target: `__folder__${parent}`,
            strength: 0.6
          });
        }
      }
    });

    // Connect agents and tools to a central hub
    const agentNodes = nodes.filter(n => n.type === "agent" || n.type === "tool");
    agentNodes.forEach(a => {
      // Connect agent/tool to some related folder nodes
      const jarvisFolder = folderMap["jarvis/core/agents"] || folderMap["jarvis/core"];
      if (jarvisFolder) {
        syntheticLinks.push({ source: a.id, target: jarvisFolder.id, strength: 0.3 });
      }
    });

    const allLinks = [...backendLinks.map(l => ({
      source: l.from || l.source,
      target: l.to || l.target,
      strength: 0.5
    })), ...syntheticLinks];

    return {
      nodes: [...nodes, ...folderNodes],
      links: allLinks
    };
  }, [rawData]);

  const stats = useMemo(() => {
    const s = { total: data.nodes.length, files: 0, agents: 0, tools: 0, folders: 0 };
    data.nodes.forEach(n => {
      if (n.type === "file") s.files++;
      else if (n.type === "agent") s.agents++;
      else if (n.type === "tool") s.tools++;
      else if (n.type === "project") s.folders++;
    });
    return s;
  }, [data]);

  // D3 force simulation — organic, neural spider layout
  useEffect(() => {
    if (!svgRef.current || !containerRef.current) return;
    if (data.nodes.length === 0) return;

    const width = containerRef.current.clientWidth || 800;
    const height = containerRef.current.clientHeight || 600;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    // Radial gradient defs for glow
    const defs = svg.append("defs");
    Object.entries(NODE_COLORS).forEach(([type, color]) => {
      const grad = defs.append("radialGradient").attr("id", `glow-${type}`);
      grad.append("stop").attr("offset", "0%").attr("stop-color", color).attr("stop-opacity", 0.8);
      grad.append("stop").attr("offset", "60%").attr("stop-color", color).attr("stop-opacity", 0.15);
      grad.append("stop").attr("offset", "100%").attr("stop-color", color).attr("stop-opacity", 0);
    });

    const g = svg.append("g").attr("class", "graph-container");
    svg.call(d3.zoom().scaleExtent([0.05, 6]).on("zoom", (e) => g.attr("transform", e.transform)));

    // Organic force: strong repulsion, weak centering, variable link distance
    const sim = d3.forceSimulation(data.nodes)
      .force("link", d3.forceLink(data.links)
        .id(d => d.id)
        .distance(d => {
          const s = d.source.type || "file";
          const t = d.target.type || "file";
          if (s === "project" || t === "project") return 30 + Math.random() * 20;
          return 50 + Math.random() * 40;
        })
        .strength(d => d.strength || 0.2)
      )
      .force("charge", d3.forceManyBody()
        .strength(d => {
          if (d.type === "agent") return -300;
          if (d.type === "tool") return -200;
          if (d.type === "project") return -150;
          return -40;
        })
      )
      .force("center", d3.forceCenter(width / 2, height / 2).strength(0.03))
      .force("collide", d3.forceCollide().radius(d => neuronRadius(d) + 2))
      .alphaDecay(0.015)
      .velocityDecay(0.4);

    simRef.current = sim;

    // Links — thin neural tendrils with curvature
    const link = g.append("g").selectAll("path")
      .data(data.links)
      .join("path")
      .attr("fill", "none")
      .attr("stroke", d => {
        const sType = (typeof d.source === 'object' ? d.source.type : null) || "file";
        return colorOf(sType);
      })
      .attr("stroke-opacity", 0.08)
      .attr("stroke-width", d => d.strength > 0.5 ? 1.2 : 0.5);

    // Glow circles behind neuron nodes (agents/tools only)
    const glow = g.append("g").selectAll("circle")
      .data(data.nodes.filter(n => n.type === "agent" || n.type === "tool"))
      .join("circle")
      .attr("r", d => neuronRadius(d) * 3)
      .attr("fill", d => `url(#glow-${d.type})`)
      .style("pointer-events", "none");

    // Nodes — tiny glowing neurons
    const node = g.append("g").selectAll("circle.neuron")
      .data(data.nodes)
      .join("circle")
      .attr("class", "neuron")
      .attr("r", d => neuronRadius(d))
      .attr("fill", d => colorOf(d.type))
      .attr("stroke", d => d.type === "project" ? colorOf(d.type) : "none")
      .attr("stroke-width", d => d.type === "project" ? 1 : 0)
      .attr("stroke-opacity", 0.5)
      .style("cursor", "pointer")
      .style("filter", d => (d.type === "agent" || d.type === "tool") ? `drop-shadow(0 0 4px ${colorOf(d.type)})` : "none")
      .call(d3.drag()
        .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.2).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
      )
      .on("mouseover", (event, d) => { setHoverNode(d); setMousePos({ x: event.clientX, y: event.clientY }); })
      .on("mousemove", (event) => setMousePos({ x: event.clientX, y: event.clientY }))
      .on("mouseout", () => setHoverNode(null))
      .on("click", (event, d) => { event.stopPropagation(); setSelectedNode(d); });

    // Labels for agents, tools, and folder nodes
    const label = g.append("g").selectAll("text")
      .data(data.nodes.filter(n => n.type !== "file"))
      .join("text")
      .text(d => d.label)
      .attr("font-size", d => d.type === "agent" ? 10 : 8)
      .attr("fill", d => colorOf(d.type))
      .attr("fill-opacity", 0.7)
      .attr("text-anchor", "middle")
      .attr("dy", d => neuronRadius(d) + 12)
      .attr("font-family", "'Inter', sans-serif")
      .style("pointer-events", "none");

    sim.on("tick", () => {
      link.attr("d", d => {
        const dx = d.target.x - d.source.x;
        const dy = d.target.y - d.source.y;
        const dr = Math.sqrt(dx * dx + dy * dy) * (1.2 + Math.random() * 0.3);
        return `M${d.source.x},${d.source.y}A${dr},${dr} 0 0,1 ${d.target.x},${d.target.y}`;
      });
      node.attr("cx", d => d.x).attr("cy", d => d.y);
      glow.attr("cx", d => d.x).attr("cy", d => d.y);
      label.attr("x", d => d.x).attr("y", d => d.y);
    });

    // Click background to deselect
    svg.on("click", () => setSelectedNode(null));

    return () => { sim.stop(); };
  }, [data]);

  if (loading || error || data.nodes.length === 0) {
    return (
      <div style={{ flex: 1, backgroundColor: "#050508", display: "flex", justifyContent: "center", alignItems: "center", height: "100%", flexDirection: "column", gap: 16 }}>
        <div style={{ width: 14, height: 14, background: "#7C3AED", borderRadius: "50%", animation: "pulse 2s ease-in-out infinite", boxShadow: "0 0 20px #7C3AED" }} />
        <div style={{ color: "#7C3AED", fontSize: 14, fontFamily: "'Inter', sans-serif", letterSpacing: 1 }}>
          {loading ? "Mapping neural network..." : error ? "Jarvis offline" : "Knowledge graph building..."}
        </div>
        <div style={{ color: "#444", fontSize: 11, fontFamily: "'Inter', sans-serif" }}>
          Chat with Jarvis to populate the graph
        </div>
        <style>{`@keyframes pulse { 0%,100% { opacity: 0.3; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1.4); } }`}</style>
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{ position: "relative", flex: 1, backgroundColor: "#050508", height: "100%", overflow: "hidden" }}>
      <svg ref={svgRef} style={{ width: "100%", height: "100%", display: "block" }} />

      {/* Legend */}
      <div style={{ position: "absolute", top: 16, right: selectedNode ? 296 : 16, transition: "right 0.3s", background: "rgba(5,5,8,0.9)", border: "1px solid #1a1a2e", padding: "10px 14px", borderRadius: 8, backdropFilter: "blur(8px)", pointerEvents: "none" }}>
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: color, boxShadow: `0 0 4px ${color}` }} />
            <span style={{ color: "#777", fontSize: 10, fontFamily: "'Inter', sans-serif" }}>{TYPE_LABELS[type] || type}</span>
          </div>
        ))}
      </div>

      {/* Stats */}
      <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 32, background: "rgba(5,5,8,0.95)", borderTop: "1px solid #1a1a2e", display: "flex", alignItems: "center", padding: "0 16px", gap: 20, fontSize: 10, color: "#555", fontFamily: "'JetBrains Mono', monospace", zIndex: 10 }}>
        <span style={{ color: "#888" }}>{stats.total} nodes</span>
        <span>{stats.files} files</span>
        <span>{stats.folders} folders</span>
        <span style={{ color: "#A855F7" }}>{stats.agents} agents</span>
        <span style={{ color: "#EC4899" }}>{stats.tools} tools</span>
        <span style={{ color: "#555" }}>{data.links.length} synapses</span>
      </div>

      {/* Detail panel */}
      <div style={{ position: "absolute", top: 0, bottom: 32, right: selectedNode ? 0 : -280, width: 280, background: "rgba(8,8,14,0.97)", borderLeft: "1px solid #1a1a2e", transition: "right 0.3s cubic-bezier(0.4, 0, 0.2, 1)", backdropFilter: "blur(12px)", display: "flex", flexDirection: "column", zIndex: 20 }}>
        {selectedNode && (
          <div style={{ padding: 20, flex: 1, overflowY: "auto", fontFamily: "'Inter', sans-serif", color: "#ddd" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: colorOf(selectedNode.type), lineHeight: 1.3, wordBreak: "break-word" }}>{selectedNode.label || selectedNode.id}</h2>
              <button onClick={() => setSelectedNode(null)} style={{ background: "none", border: "none", color: "#555", cursor: "pointer", fontSize: 14, padding: "0 4px" }}>x</button>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 16, background: "#111", padding: "4px 8px", borderRadius: 4, width: "max-content" }}>
              <div style={{ width: 5, height: 5, borderRadius: "50%", background: colorOf(selectedNode.type), boxShadow: `0 0 6px ${colorOf(selectedNode.type)}` }} />
              <span style={{ fontSize: 10, color: "#888", textTransform: "uppercase", letterSpacing: 1 }}>{TYPE_LABELS[selectedNode.type] || selectedNode.type}</span>
            </div>

            <div style={{ display: "flex", gap: 16, marginBottom: 24 }}>
              <div>
                <div style={{ fontSize: 9, color: "#555", textTransform: "uppercase", marginBottom: 4 }}>Connections</div>
                <div style={{ fontSize: 14, fontWeight: 500 }}>{selectedNode.connection_count || 0}</div>
              </div>
            </div>

            {selectedNode.id && (
              <div style={{ fontSize: 11, color: "#444", wordBreak: "break-all", marginTop: 8, fontFamily: "'JetBrains Mono', monospace" }}>
                {selectedNode.id}
              </div>
            )}

            {selectedNode.properties && Object.keys(selectedNode.properties).length > 0 && (
              <>
                <div style={{ fontSize: 9, color: "#555", textTransform: "uppercase", marginBottom: 8, marginTop: 20, letterSpacing: 1 }}>Properties</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4, background: "#0a0a10", padding: 10, borderRadius: 6, border: "1px solid #1a1a2e" }}>
                  {Object.entries(selectedNode.properties).map(([k, v]) => (
                    <div key={k} style={{ fontSize: 11, wordBreak: "break-word" }}>
                      <span style={{ color: "#555" }}>{k}: </span><span style={{ color: "#aaa" }}>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Hover tooltip */}
      {hoverNode && !selectedNode && (
        <div style={{ position: "fixed", left: mousePos.x + 16, top: mousePos.y + 16, background: "rgba(8,8,14,0.97)", border: `1px solid ${colorOf(hoverNode.type)}33`, padding: "8px 12px", borderRadius: 6, pointerEvents: "none", zIndex: 30, color: "#FFF", fontFamily: "'Inter', sans-serif", maxWidth: 240, boxShadow: `0 4px 20px rgba(0,0,0,0.6), 0 0 8px ${colorOf(hoverNode.type)}22` }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: colorOf(hoverNode.type), marginBottom: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{hoverNode.label || hoverNode.id}</div>
          <div style={{ fontSize: 10, color: "#666" }}>{TYPE_LABELS[hoverNode.type] || hoverNode.type}</div>
        </div>
      )}
    </div>
  );
}
