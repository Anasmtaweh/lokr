from pathlib import Path
from typing import Any, List, Dict, Optional, Set
import re

from core.scanner import CodeScanner

class ContextOracle:
    """
    The "Brain" of the DevOps Context Oracle.
    Fuses semantic Vector DB search, brute-force keyword scanning, AST parsing,
    and dependency graph traversal to generate rich context for LLM prompting.
    """

    def __init__(self, parser: Any, graph: Any, db: Any) -> None:
        """
        Stores references to the initialized Phase 2, 3, and 4 engine components.

        Args:
            parser (Any): An initialized CodeParser instance.
            graph (Any): An initialized DependencyGraph instance with the graph already built.
            db (Any): An initialized CodebaseVectorDB instance.
        """
        self.parser = parser
        self.graph = graph
        self.db = db

    def _extract_keywords(self, query: str) -> Set[str]:
        """
        Heuristic to extract 'uncommon' words (length > 5 or underscores).
        Ignores common stop words.
        """
        words = re.findall(r'\w+', query.lower())
        stop_words = {
            "the", "and", "for", "with", "from", "this", "that", "these", 
            "those", "what", "where", "how", "when", "about", "project"
        }
        keywords = {
            w for w in words 
            if w not in stop_words and (len(w) > 5 or "_" in w)
        }
        return keywords

    def generate_context(self, query: str, top_k: int = 3, allowed_files: Optional[List[Path]] = None) -> str:
        """
        Generates a rich, structured Markdown context block by:
          1. Blending semantic search with brute-force keyword scanning (Hybrid Search).
          2. Applying deterministic routing (boosting) for explicitly named files.
          3. Parsing each file's AST and fetching dependents.
          4. Injecting actual source code for deep logic grounding.
        """
        # Step 1: Detect Keywords for Brute-Force Fallback
        keywords = self._extract_keywords(query)
        
        # Step 2: Determine Search Scope
        files_to_scan = allowed_files
        if files_to_scan is None:
            # Fallback to a full scan if no filters are provided
            scanner = CodeScanner(target_dir=Path(".").resolve())
            files_to_scan = list(scanner.get_files())

        # Step 3: Brute-Force Keyword Scan (Combatting Vector DB Truncation)
        keyword_results: List[Dict[str, Any]] = []
        for file_path in files_to_scan:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().lower()
                
                hits = sum(1 for kw in keywords if kw in content)
                if hits > 0:
                    # Map hits to a distance metric (more hits = lower distance)
                    # Use 0.5 as a neutral starting point for hybrid merge
                    keyword_results.append({
                        "file_path": str(file_path.resolve()),
                        "distance": 0.5 - (hits * 0.05),
                        "source": "keyword"
                    })
            except Exception:
                continue

        # Step 4: Semantic search (cast a wide net)
        raw_semantic: List[Dict[str, Any]] = self.db.search(query, n_results=10)

        # Apply File Filtering to Semantic results
        if allowed_files is not None:
            allowed_strs = set(str(f.resolve()) for f in allowed_files)
            raw_semantic = [r for r in raw_semantic if r.get("file_path") in allowed_strs]

        # Step 5: Hybrid Merge (Blend Semantic & Keywords)
        merged_map: Dict[str, Dict[str, Any]] = {r["file_path"]: r for r in raw_semantic}
        for kr in keyword_results:
            path = kr["file_path"]
            if path in merged_map:
                # If found in both, give it a significant relevance boost
                merged_map[path]["distance"] -= 0.2
            else:
                merged_map[path] = kr

        # Step 6: Deterministic Routing (Filename Boosting)
        query_lower = query.lower()
        hybrid_results = list(merged_map.values())
        for res in hybrid_results:
            file_path_str = res.get("file_path", "")
            if file_path_str:
                fname = Path(file_path_str).name.lower()
                # If the filename itself is in the query, it MUST be rank #1
                if fname in query_lower:
                    res["distance"] -= 1000.0

        # Re-sort and slice to top_k
        hybrid_results.sort(key=lambda x: x.get("distance", 0.0))
        search_results = hybrid_results[:top_k]

        # Step 7: Build the output block list
        blocks: List[str] = [
            f"# Context Oracle Output\n**User Query:** {query}\n"
        ]

        if not search_results:
            blocks.append("_No relevant files found in the active workspace._")
            return "\n".join(blocks)

        # Step 8: Loop through matched files and build detailed Markdown sections
        for result in search_results:
            file_path_str: str = result.get("file_path", "")
            distance: float = result.get("distance", 0.0)

            if not file_path_str:
                continue

            file_path = Path(file_path_str)

            # --- Parse AST ---
            try:
                ast_data: Dict[str, Any] = self.parser.parse_file(file_path)
            except Exception:
                ast_data = {"imports": [], "classes": [], "functions": []}

            classes: List[str] = [c.get("name", "") for c in ast_data.get("classes", [])]
            functions: List[str] = [
                f"def {f.get('name', '')}({', '.join(f.get('parameters', []))})"
                for f in ast_data.get("functions", [])
            ]

            # --- Get Dependents ---
            try:
                dependents: List[str] = self.graph.get_dependents(file_path)
            except Exception:
                dependents = []

            # --- Format Dependents section ---
            if dependents:
                dep_lines = "\n".join(f"- `{Path(d).name}`" for d in dependents)
            else:
                dep_lines = "- _None detected_"

            # --- Format Classes section ---
            classes_str = ", ".join(f"`{c}`" for c in classes) if classes else "_None_"

            # --- Format Functions section ---
            if functions:
                funcs_str = "\n".join(f"  - `{fn}`" for fn in functions)
            else:
                funcs_str = "  - _None_"

            # --- Read Source Code ---
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    source_code = f.read()
            except Exception as e:
                source_code = f"Error reading source code: {e}"

            # --- Assemble the Markdown block for this file ---
            block = (
                f"---\n"
                f"## File: `{file_path_str}`\n"
                f"**Relevance Rank:** `{distance:.4f}`\n\n"
                f"### 🔗 Dependencies (Files that import this):\n"
                f"{dep_lines}\n\n"
                f"### 🧬 File Structure (AST):\n"
                f"- **Classes:** {classes_str}\n"
                f"- **Functions:**\n{funcs_str}\n\n"
                f"### 💻 Actual Source Code:\n"
                f"```python\n"
                f"{source_code}\n"
                f"```\n"
            )
            blocks.append(block)

        # Step 9: Join and return the full context
        return "\n".join(blocks)
