from typing import List, Dict, Any
from pathlib import Path

def get_snippet(filepath: str, start: int, end: int) -> str:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        safe_start = max(0, start - 1)
        safe_end = min(len(lines), end)
        return "".join(lines[safe_start:safe_end])
    except Exception:
        return ""

def format_node_for_embedding(node_id: str, node_data: Dict[str, Any]) -> str:
    """
    Formats a node into a rich string for semantic embedding, including actual code snippets.
    """
    filepath = node_id.split("::")[0]
    name = node_data.get("name", "unknown")
    node_type = node_data.get("node_type", "function")
    docstring = node_data.get("docstring") or "No docstring provided."
    
    start_line = node_data.get("lineno")
    end_line = node_data.get("end_lineno")
    snippet = node_data.get("source_code", "")
    if start_line and end_line and not snippet:
        snippet = get_snippet(filepath, start_line, end_line)
        # Cap snippet length to prevent blowing up the embedding context
    if len(snippet) > 800:
        snippet = snippet[:800] + "\n...[truncated]"

    if node_type == "class":
        return f"{filepath} :: Class {name}\nDocstring: {docstring}\nCode:\n{snippet}"
    elif node_type == "schema":
        return f"{filepath} :: Mongoose Schema {name}\nCode:\n{snippet}"
    elif node_type == "variable":
        return f"{filepath} :: Global Variable {name}\nCode:\n{snippet}"
    elif node_type == "config":
        return f"{filepath} :: Config Block {name}\nCode:\n{snippet}"
    elif node_type == "execution":
        return f"{filepath} :: Execution Block {name}\nCode:\n{snippet}"
    else:
        signature = node_data.get("signature", "unknown")
        return f"{filepath} :: {name}\nSignature: {signature}\nDocstring: {docstring}\nCode:\n{snippet}"

class Indexer:
    """
    Orchestrates the embedding process by bridgeing the Gap between 
    the DependencyGraph and the CodebaseVectorDB.
    """
    def __init__(self, vector_db) -> None:
        self.vector_db = vector_db

    def index_nodes(self, graph) -> None:
        """
        Indexes all function and class nodes currently present in the graph.
        """
        nodes = [n for n, d in graph.graph.nodes(data=True) if d.get("node_type") in ("function", "class", "schema", "variable", "config", "execution")]
        self.index_node_list(nodes, graph)

    def index_node_list(self, node_ids: List[str], graph) -> None:
        """
        Formats and indexes a specific list of node IDs.
        """
        if not node_ids:
            return

        documents = []
        metadatas = []
        ids = []

        for nid in node_ids:
            if nid not in graph.graph:
                continue
            node_data = graph.graph.nodes[nid]
            node_type = node_data.get("node_type")
            
            # Index classes, functions, schemas, variables, configs, executions
            if node_type not in ("function", "class", "schema", "variable", "config", "execution"):
                continue
            
            doc = format_node_for_embedding(nid, node_data)
            documents.append(doc)
            metadatas.append({
                "file_path": nid.split("::")[0],
                "name": node_data.get("name"),
                "node_type": node_type
            })
            ids.append(nid)
        
        if ids:
            self.vector_db.upsert_nodes(documents, metadatas, ids)

    def delete_nodes(self, node_ids: List[str]) -> None:
        """
        Passthrough to delete nodes from the vector store.
        """
        self.vector_db.delete_nodes(node_ids)
