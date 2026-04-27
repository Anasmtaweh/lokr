from pathlib import Path
from typing import Any, List, Dict, Optional, Set
import re

from core.scanner import CodeScanner
from core.retriever import Retriever

class ContextOracle:
    """
    The "Brain" of the DevOps Context Oracle.
    Fuses semantic Vector DB search, brute-force keyword scanning, AST parsing,
    and dependency graph traversal to generate rich context for LLM prompting.
    """

    def __init__(self, parser: Any, graph: Any, db: Any, graph_path: Optional[str] = None, reasoning_memory: Optional[Any] = None, project_root: Optional[Path] = None) -> None:
        """
        Stores references to the initialized Phase 2, 3, and 4 engine components.

        Args:
            parser (Any): An initialized CodeParser instance.
            graph (Any): An initialized DependencyGraph instance with the graph already built.
            db (Any): An initialized CodebaseVectorDB instance.
            reasoning_memory (Optional[ReasoningMemory]): Persistent reasoning memory.
        """
        self.parser = parser
        self.graph = graph
        self.db = db
        self.retriever = Retriever(db, graph)
        self.graph_path = Path(graph_path) if graph_path else None
        self.reasoning_memory = reasoning_memory
        self.project_root = project_root

    def _include_explicit_files(self, query: str) -> str:
        if not self.project_root:
            return ""
            
        pattern = r'\b[\w./-]+\.[a-zA-Z]{2,4}\b'
        matches = set(re.findall(pattern, query))
        
        file_blocks = []
        for match in matches:
            if match.startswith(('http:', 'https:', 'www.')):
                continue
                
            try:
                filepath = (self.project_root / match).resolve()
                
                if not str(filepath).startswith(str(self.project_root.resolve())):
                    file_blocks.append(f"### 📄 SYSTEM LOG: ACCESS DENIED to {match}. Path traversal detected.")
                    continue
                    
                if filepath.is_file():
                    if filepath.stat().st_size > 1_000_000:
                        file_blocks.append(f"### 📄 Full file: {match}\n_File too large to include. (Exceeds 1MB)_\n")
                        continue
                        
                    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                        
                    facts = []
                    if filepath.suffix in ['.js', '.jsx', '.ts', '.tsx']:
                        funcs = re.findall(r'(?:async\s+)?function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?\(', content)
                        classes = re.findall(r'class\s+(\w+)', content)
                        facts.extend([f"Function: {m[0] or m[1]}" for m in funcs])
                        facts.extend([f"Class: {c}" for c in classes])
                    elif filepath.suffix == '.py':
                        funcs = re.findall(r'^def\s+(\w+)', content, re.MULTILINE)
                        classes = re.findall(r'^class\s+(\w+)', content, re.MULTILINE)
                        facts.extend([f"Function: {f}" for f in funcs])
                        facts.extend([f"Class: {c}" for c in classes])

                    if facts:
                        facts_str = "\n".join(f" - {f}" for f in facts)
                        file_blocks.append(f"### 📄 FILE FACTS (verified)\n{facts_str}\n")
                        
                    lang = "javascript" if filepath.suffix in [".js", ".jsx", ".ts", ".tsx"] else "python"
                    file_blocks.append(f"### 📄 Full file: {match}\n```{lang}\n{content}\n```\n")
                else:
                    file_blocks.append(f"### 📄 SYSTEM LOG: FILE NOT FOUND. {match} does not exist in the project root.")
            except Exception as e:
                print(f"[WARN] Could not read explicit file {match}: {e}")
                
        return "\n".join(file_blocks)

    def generate_context(self, query: str, top_k: int = 5) -> tuple[str, Set[str], Set[str]]:
        """
        Generates a rich, execution-aware context block.
        Now returns the context string and the underlying nodes for visualization.
        """
        blocks: List[str] = [
            f"# Context Oracle Output\n**User Query:** {query}\n"
        ]

        # Step 1 & 2: Search and Expand via Retriever
        center_nodes, expanded_node_ids = self.retriever.search_and_expand(query, top_k=top_k)
        
        if not expanded_node_ids:
            blocks.append("_No relevant function nodes found in the active workspace._")
            return "\n".join(blocks), set(), set()

        # Step 3: Build Context from Nodes
        print(f"[*] Expanded context to {len(expanded_node_ids)} relevant function nodes.")
        context_body = self.retriever.build_context(expanded_node_ids)
        
        # Step 4: Update Usage Statistics (Feedback Loop)
        weights = {nid: 1 for nid in expanded_node_ids}
        for nid in center_nodes:
            weights[nid] = 2  # Boost semantic hits
        
        self.graph.increment_usage(weights)
        if self.graph_path:
            self.graph.save_graph(self.graph_path)

        # Step 5: Update Reasoning Memory (Persistent logical links)
        if self.reasoning_memory:
            self.reasoning_memory.record_reasoning_path(expanded_node_ids, query)
            self.reasoning_memory.save()

        explicit_files_content = self._include_explicit_files(query)
        if explicit_files_content:
            blocks.append("### 📂 Explicitly Requested Files:\n")
            blocks.append(explicit_files_content)

        blocks.append("### 🧪 Execution-Aware Context (Call Graph Expanded):\n")
        blocks.append("```python\n" + context_body + "\n```")

        # Step 4: Join and return the full context
        return "\n".join(blocks), center_nodes, expanded_node_ids
