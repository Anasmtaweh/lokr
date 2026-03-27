import networkx as nx
from pathlib import Path
from typing import List, Dict, Any

class DependencyGraph:
    """
    Constructs a directed dependency graph of the codebase using NetworkX.
    Nodes are file paths, and edges represent import dependencies 
    (Source File -> Imported File).
    """

    def __init__(self) -> None:
        """
        Initializes an empty directed graph.
        """
        self.graph = nx.DiGraph()

    def build_graph(self, file_paths: List[Path], parser: Any) -> None:
        """
        Iterates over the given file paths, parses their AST, extracts imports,
        and builds corresponding nodes and directed edges in the graph.

        Args:
            file_paths (List[Path]): A list of absolute or relative file paths in the project.
            parser (Any): An instance of CodeParser to extract imports.
        """
        # Add all valid files as nodes first
        for fp in file_paths:
            self.graph.add_node(str(fp.resolve()))

        # Build edges
        for fp in file_paths:
            abs_fp = fp.resolve()
            try:
                parsed_data: Dict[str, Any] = parser.parse_file(abs_fp)
                imports: List[str] = parsed_data.get("imports", [])
                
                for imp_str in imports:
                    imported_file = self._resolve_import_to_file(imp_str, file_paths)
                    if imported_file:
                        # Edge: Current File -> Imported File
                        self.graph.add_edge(str(abs_fp), str(imported_file))
            except Exception as e:
                # Log or ignore files that fail to parse
                continue

    def _resolve_import_to_file(self, import_str: str, available_files: List[Path]) -> str | None:
        """
        Internal heuristic to convert an import string to a local project file path.
        Handles standard 'import module.submodule' and 'from module import x'.

        Args:
            import_str (str): The raw string extracted from the AST.
            available_files (List[Path]): The list of valid project files.

        Returns:
            str | None: The absolute path string of the imported file if found, else None.
        """
        # Determine the base module path being imported
        base_module = ""
        if import_str.startswith("from "):
            # "from core.scanner import CodeScanner" -> "core.scanner"
            parts = import_str.split(" ")
            if len(parts) >= 2:
                base_module = parts[1]
        else:
            # "import core.parser" -> "core.parser"
            # we handle aliasing ("import json as j") by stripping down to the dotted name
            base_module = import_str.split(" ")[0]

        if not base_module:
            return None

        # Convert module dotted path to posix slash path (e.g., core.scanner -> core/scanner)
        module_path = base_module.replace(".", "/")

        # Match against our known valid files
        for valid_file in available_files:
            rel_path_str = valid_file.as_posix()
            
            # Match direct file (e.g. core/scanner.py)
            if rel_path_str.endswith(f"{module_path}.py"):
                return str(valid_file.resolve())
            
            # Match package init (e.g. core/scanner/__init__.py)
            if rel_path_str.endswith(f"{module_path}/__init__.py"):
                return str(valid_file.resolve())

        return None

    def get_dependents(self, target_filepath: Path) -> List[str]:
        """
        Returns a list of all files that import the target_filepath.
        In this DiGraph (A -> B means A imports B), the dependents of B are its predecessors.

        Args:
            target_filepath (Path): The file we want to find dependents for.

        Returns:
            List[str]: A list of absolute paths of files that import the target.
        """
        abs_target = str(target_filepath.resolve())
        
        if abs_target not in self.graph:
            return []
            
        # Get predecessors (nodes that point TO the target node)
        predecessors = list(self.graph.predecessors(abs_target))
        return predecessors
