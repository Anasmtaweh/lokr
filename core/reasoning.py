import networkx as nx
import json
from pathlib import Path
from typing import Set, Dict, List, Any, Optional

class ReasoningMemory:
    """
    Manages the persistent Global Reasoning Graph.
    This graph links code nodes based on their co-occurrence in retrieval paths,
    effectively building a 'logic map' of the codebase as it is queried.
    """

    def __init__(self, storage_path: str | Path) -> None:
        self.storage_path = Path(storage_path)
        self.graph = nx.Graph()
        self._load()

    def _load(self) -> None:
        """Loads the reasoning graph from disk if it exists."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                self.graph = nx.node_link_graph(data)
                print(f"[*] Loaded Reasoning Memory with {len(self.graph.nodes)} nodes.")
            except Exception as e:
                print(f"[!] Failed to load reasoning memory: {e}")
                self.graph = nx.Graph()
        else:
            self.graph = nx.Graph()

    def record_reasoning_path(self, nodes: Set[str], query: str) -> None:
        """
        Records a set of nodes retrieved for a specific query.
        Creates/reinforces edges between all nodes in the set.
        """
        node_list = list(nodes)
        
        # Add nodes with initial metadata
        for nid in node_list:
            if nid not in self.graph:
                self.graph.add_node(nid, query_hits=1)
            else:
                self.graph.nodes[nid]['query_hits'] = self.graph.nodes[nid].get('query_hits', 0) + 1

        # Create/reinforce clique (fully connected subgraph) for this reasoning path
        # This represents that these nodes are "semantically related in reasoning"
        for i in range(len(node_list)):
            for j in range(i + 1, len(node_list)):
                u, v = node_list[i], node_list[j]
                if self.graph.has_edge(u, v):
                    self.graph[u][v]['weight'] = self.graph[u][v].get('weight', 0) + 1
                else:
                    self.graph.add_edge(u, v, weight=1)

    def save(self) -> None:
        """Persists the reasoning graph to disk."""
        try:
            self.storage_path.parent.mkdir(exist_ok=True)
            data = nx.node_link_data(self.graph)
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[!] Failed to save reasoning memory: {e}")

    def get_related_nodes(self, node_id: str, limit: int = 5) -> List[str]:
        """Retrieves nodes most strongly linked to the given node in past reasoning."""
        if node_id not in self.graph:
            return []
            
        neighbors = []
        for n in self.graph.neighbors(node_id):
            weight = self.graph[node_id][n].get('weight', 1)
            neighbors.append((n, weight))
            
        # Sort by weight descending
        neighbors.sort(key=lambda x: x[1], reverse=True)
        return [n[0] for n in neighbors[:limit]]
