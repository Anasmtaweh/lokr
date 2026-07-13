import networkx as nx
from pathlib import Path
from typing import List, Dict, Any, Set

class Retriever:
    """
    Handles semantic search results and performs graph-guided expansion 
    to retrieve execution-aware context.
    """
    def __init__(self, db, graph) -> None:
        self.db = db
        self.graph = graph

    def search_and_expand(self, query: str, top_k: int = 15) -> tuple[Set[str], Set[str]]:
        """
        Performs semantic search followed by a 1-hop expansion of the call graph.
        
        Returns:
            Tuple[Set[str], Set[str]]: (initial_semantic_hits, fully_expanded_set)
        """
        import re
        
        # Step 0: Route Signature Heuristic (BUG 3)
        # E.g., user asks "delete pet", we look for "DELETE::/admin/pets/:id"
        route_hits = set()
        query_lower = query.lower()
        route_methods = ['get', 'post', 'put', 'delete', 'patch']
        
        has_route_keyword = any(m in query_lower for m in route_methods)
        if has_route_keyword:
            # Simple keyword extraction (ignore common words)
            keywords = [w for w in query_lower.split() if w not in ['how', 'is', 'a', 'the', 'in', 'directly', 'what', 'where']]
            for n, d in self.graph.graph.nodes(data=True):
                if d.get('node_type') == 'function':
                    name = d.get('name', '').lower()
                    if '::' in name and any(name.startswith(m + '::') for m in route_methods):
                        # Calculate match score based on keywords present in the route path
                        route_path = name.split('::')[1]
                        match_count = sum(1 for kw in keywords if kw in route_path or kw in name.split('::')[0])
                        if match_count >= 2: # At least method + one path keyword
                            route_hits.add(n)

        # Step 0.5: Global Architecture Heuristic
        global_hits = set()
        global_keywords = [
            'entire project', 'overview', 'architecture', 'explain this', 'explain the', 
            'vibe coder', 'summary', 'high level', 'tech stack', 'frameworks', 
            'youtube terms', 'master this project'
        ]
        is_global_query = any(k in query_lower for k in global_keywords)
        
        if is_global_query:
            for n, d in self.graph.graph.nodes(data=True):
                if d.get('node_type') == 'file':
                    lower_n = n.lower()
                    if 'readme.md' in lower_n or 'package.json' in lower_n or 'requirements.txt' in lower_n:
                        global_hits.add(n)
                    elif lower_n.endswith('/app.js') or lower_n.endswith('/index.js') or lower_n.endswith('/main.py') or lower_n.endswith('/app.py'):
                        global_hits.add(n)

        # Step 0.7: Exact Symbol / Keyword Heuristic
        # Boosts exact matches like "mongoose.connect" or "jwt.sign"
        keyword_hits = set()
        symbols = [w for w in query.split() if len(w) > 3 and not w.lower() in ['what', 'where', 'how', 'when', 'why', 'the', 'is', 'are', 'does', 'do', 'in', 'on', 'at', 'this']]
        
        if symbols:
            for n, d in self.graph.graph.nodes(data=True):
                name = d.get('name', '')
                if any(sym in name for sym in symbols):
                    keyword_hits.add(n)

        # Step 1: Semantic Search
        results = self.db.search(query, n_results=top_k)
        initial_node_ids = {res["node_id"] for res in results if res.get("node_id")}
        
        # Filter out scratch/mock/test files to prevent hallucinations
        initial_node_ids = {nid for nid in initial_node_ids if '/scratch/' not in nid and 'mock' not in nid.lower() and '/test/' not in nid}
        
        # Inject exact route hits
        initial_node_ids.update(route_hits)
        
        # Inject global hits
        initial_node_ids.update(global_hits)
        
        # Inject exact keyword hits
        initial_node_ids.update(keyword_hits)
        
        # Filter out stale IDs that no longer exist in the current graph
        initial_node_ids = {nid for nid in initial_node_ids if nid in self.graph.graph}
        
        if is_global_query and global_hits:
            # Skip deep 1-hop expansion for global queries to prevent noise
            # and just return the root architectural files.
            return initial_node_ids, set(initial_node_ids)

        # Step 2: 1-Hop Expansion
        context_node_ids = set(initial_node_ids)
        for node_id in initial_node_ids:
            if node_id not in self.graph.graph:
                continue
            
            # Callees & Dependencies (Successors)
            for _, neighbor, data in self.graph.graph.out_edges(node_id, data=True):
                edge_type = data.get('edge_type')
                if edge_type in ('calls', 'depends_on', 'parent_schema', 'resolves_to'):
                    context_node_ids.add(neighbor)
                    
                    # If we follow a 'resolves_to' to a FILE, also pull what that file CONTAINS
                    if edge_type == 'resolves_to':
                        for _, sub_neighbor, sub_data in self.graph.graph.out_edges(neighbor, data=True):
                            if sub_data.get('edge_type') == 'contains':
                                context_node_ids.add(sub_neighbor)
            
            # Callers & Dependents (Predecessors)
            for neighbor, _, data in self.graph.graph.in_edges(node_id, data=True):
                edge_type = data.get('edge_type')
                if edge_type in ('calls', 'depends_on', 'parent_schema'):
                    context_node_ids.add(neighbor)
            
            # --- Upward Expansion (Parent Classes AND Parent Files) ---
            # For each retrieved node, pull in the parent class or parent file
            # so top-level initialization code (mongoose.connect, app.listen, etc.)
            # is always visible to the LLM.
            for neighbor, _, data in self.graph.graph.in_edges(node_id, data=True):
                if data.get('edge_type') == 'contains':
                    pred_data = self.graph.graph.nodes[neighbor]
                    if pred_data.get('node_type') == 'class':
                        context_node_ids.add(neighbor)
                    elif pred_data.get('node_type') == 'file':
                        # Pull in the parent file node itself so the LLM sees the top-level
                        # initialization context (like mongoose.connect, app.listen)
                        context_node_ids.add(neighbor)
        
        return initial_node_ids, context_node_ids

    def get_snippet(self, filepath: str, start: int, end: int) -> str:
        """
        Reads a specific range of lines from a source file.
        """
        try:
            path = Path(filepath)
            if not path.exists():
                return f"# Error: File not found: {filepath}"
                
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # start and end are 1-indexed
            # Ensure we don't go out of bounds
            safe_start = max(0, start - 1)
            safe_end = min(len(lines), end)
            
            snippet_lines = [f"{safe_start + i + 1} | {line}" for i, line in enumerate(lines[safe_start:safe_end])]
            return "".join(snippet_lines)
        except Exception as e:
            return f"# Error reading snippet from {filepath}: {e}"

    def build_context(self, node_ids: Set[str]) -> str:
        """
        Assembles the final context string by organizing nodes into logical 
        execution paths using topological sorting or DFS traversal.
        """
        if not node_ids:
            return ""

        # Step 1: Extract Subgraph
        # We only care about 'calls' edges between the retrieved nodes
        subgraph = self.graph.graph.subgraph(node_ids).copy()
        
        # Filter edges to keep only relevant types within the subgraph
        # We need to reverse 'depends_on' and 'parent_schema' so the dependencies come BEFORE the dependents in top-sort
        edges_to_remove = []
        edges_to_add = []
        for u, v, d in subgraph.edges(data=True):
            edge_type = d.get('edge_type')
            if edge_type not in ('calls', 'contains', 'depends_on', 'parent_schema'):
                edges_to_remove.append((u, v))
            elif edge_type in ('depends_on', 'parent_schema'):
                edges_to_remove.append((u, v))
                edges_to_add.append((v, u, d)) # Reverse edge for ordering
                
        subgraph.remove_edges_from(edges_to_remove)
        subgraph.add_edges_from(edges_to_add)

        # Step 2: Determine Ordering
        ordered_nodes = []
        try:
            if nx.is_directed_acyclic_graph(subgraph):
                ordered_nodes = list(nx.topological_sort(subgraph))
            else:
                # Fallback for cyclic graphs (e.g. recursion)
                print("[!] Detected call cycle, falling back to DFS ordering.")
                # Find "roots" (nodes with in-degree 0)
                roots = [n for n, d in subgraph.in_degree() if d == 0]
                if not roots:
                    # If it's a strongly connected component, just pick the first node
                    roots = [list(subgraph.nodes())[0]]
                
                visited = set()
                for root in roots:
                    for node in nx.dfs_preorder_nodes(subgraph, root):
                        if node not in visited:
                            ordered_nodes.append(node)
                            visited.add(node)
                
                # Add any remaining unreachable nodes
                for node in subgraph.nodes():
                    if node not in visited:
                        ordered_nodes.append(node)
                        visited.add(node)
        except Exception as e:
            print(f"[WARN] Ordering failed: {e}. Falling back to sorted list.")
            ordered_nodes = sorted(list(node_ids))

        # Step 3: Narrative Formatting
        blocks = []
        for i, nid in enumerate(ordered_nodes):
            node_data = self.graph.graph.nodes[nid]
            filepath = nid.split("::")[0]
            name = node_data.get("name", "unknown")
            start = node_data.get("lineno")
            end = node_data.get("end_lineno")
            calls = node_data.get("calls", [])
            
            # Find which node in our context calls THIS node
            callers_in_context = [
                n for n in subgraph.predecessors(nid)
            ]
            caller_names = [n.split("::")[-1] for n in callers_in_context]
            
            # Format snippet
            node_type = node_data.get("node_type", "function")
            
            if "source_code" in node_data:
                code = node_data["source_code"]
            elif node_type == 'file':
                # Grab the top 500 lines to ensure top-level setups like mongoose.connect
                # are fully captured, without dumping massive 1000-line files.
                code = self.get_snippet(filepath, 1, 500) + "\n... [Remaining file components listed individually below] ..."
            elif start and end:
                code = self.get_snippet(filepath, start, end)
            else:
                code = "# Code location metadata unavailable"

            # Build block header
            header_lines = []
            
            if i == 0:
                header_lines.append("### 🚀 Execution Path Entry Point ###\n")
            elif callers_in_context:
                header_lines.append(f"↓ Called by: {', '.join(caller_names)} ↓\n")
            else:
                header_lines.append("### 🔗 Related Context ###\n")

            line_info = f" (Lines {start}-{end})" if start and end else ""
            
            # Universal, AI-native provenance header
            header_lines.append(f"Code Snippet from `{filepath}`{line_info}:\n")
            
            # List immediate callees that are also in our context
            callees_in_context = [
                n for n in subgraph.successors(nid)
            ]
            if callees_in_context:
                callee_names = [n.split("::")[-1] for n in callees_in_context]
                # Clean any synthetic prefixes so the AI isn't confused
                clean_callees = [c.replace('EXEC::', '') for c in callee_names]
                header_lines.append(f"Calls: {', '.join([f'`{c}`' for c in clean_callees])}\n")

            lang = "javascript" if node_type in ("variable", "schema") or filepath.endswith((".js", ".ts")) else "python"

            block = (
                f"{''.join(header_lines)}\n"
                f"--- FILE: {filepath} ---\n"
                f"```{lang}\n"
                f"{code}\n"
                f"```\n"
                f"--- END FILE ---\n"
            )
            blocks.append(block)
        
        return "\n\n".join(blocks)
