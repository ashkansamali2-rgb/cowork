#!/usr/bin/env python3
"""Knowledge graph for the Cowork/Jarvis system."""
import json
import time
from pathlib import Path

GRAPH_PATH = Path("/Users/ashkansamali/cowork/jarvis/memory/knowledge_graph.json")


class KnowledgeGraph:

    def __init__(self):
        GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not GRAPH_PATH.exists():
            GRAPH_PATH.write_text(json.dumps({"nodes": {}, "edges": []}, indent=2))

    def _load(self) -> dict:
        try:
            return json.loads(GRAPH_PATH.read_text())
        except Exception:
            return {"nodes": {}, "edges": []}

    def _save(self, graph: dict):
        try:
            GRAPH_PATH.write_text(json.dumps(graph, indent=2))
        except Exception:
            pass

    def add_node(self, node_id: str, label: str, node_type: str, properties: dict = None):
        graph = self._load()
        if node_id not in graph["nodes"]:
            graph["nodes"][node_id] = {
                "id": node_id,
                "label": label,
                "type": node_type,
                "properties": properties or {},
                "created": time.time(),
                "last_active": time.time(),
                "connection_count": 0,
            }
        else:
            graph["nodes"][node_id]["last_active"] = time.time()
        self._save(graph)

    def add_edge(self, from_id: str, to_id: str, relationship: str):
        graph = self._load()
        edge = {"from": from_id, "to": to_id, "rel": relationship, "created": time.time()}
        # Avoid duplicates
        existing = [(e["from"], e["to"], e["rel"]) for e in graph["edges"]]
        if (from_id, to_id, relationship) not in existing:
            graph["edges"].append(edge)
            for nid in (from_id, to_id):
                if nid in graph["nodes"]:
                    graph["nodes"][nid]["connection_count"] = graph["nodes"][nid].get("connection_count", 0) + 1
        self._save(graph)

    def touch_node(self, node_id: str):
        graph = self._load()
        if node_id in graph["nodes"]:
            graph["nodes"][node_id]["last_active"] = time.time()
            self._save(graph)

    def get_graph_data(self) -> dict:
        graph = self._load()
        nodes = list(graph["nodes"].values())
        edges = graph["edges"]
        node_types = {}
        for n in nodes:
            t = n.get("type", "unknown")
            node_types[t] = node_types.get(t, 0) + 1
        most_connected = max(nodes, key=lambda n: n.get("connection_count", 0), default=None)
        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "node_types": node_types,
                "most_connected": most_connected["label"] if most_connected else None,
            }
        }

    def index_codebase(self):
        """Scan ~/cowork and populate initial graph nodes (batch mode)."""
        cowork = Path("/Users/ashkansamali/cowork")
        skip   = {".venv", "node_modules", "__pycache__", ".git", "venv"}

        graph = self._load()
        now = time.time()

        for py_file in cowork.rglob("*.py"):
            if any(s in py_file.parts for s in skip):
                continue
            rel = str(py_file.relative_to(cowork))
            if rel not in graph["nodes"]:
                graph["nodes"][rel] = {
                    "id": rel,
                    "label": py_file.name,
                    "type": "file",
                    "properties": {"path": str(py_file), "size": py_file.stat().st_size},
                    "created": now,
                    "last_active": now,
                    "connection_count": 0,
                }
            else:
                graph["nodes"][rel]["last_active"] = now

        # Known agents
        for agent in ["AgentRuntime", "AgentHierarchy", "MetaAgent", "SelfImproveDaemon"]:
            aid = agent.lower()
            if aid not in graph["nodes"]:
                graph["nodes"][aid] = {
                    "id": aid, "label": agent, "type": "agent",
                    "properties": {}, "created": now, "last_active": now, "connection_count": 0,
                }

        # Known tools
        tools = [
            "web_search", "fetch_url", "create_word_document",
            "create_keynote_presentation", "run_shell", "open_app",
            "speak", "write_file", "read_file", "browser_navigate",
        ]
        for tool in tools:
            if tool not in graph["nodes"]:
                graph["nodes"][tool] = {
                    "id": tool, "label": tool, "type": "tool",
                    "properties": {}, "created": now, "last_active": now, "connection_count": 0,
                }

        self._save(graph)
        print(f"[KG] Indexed {len(graph['nodes'])} nodes.")
