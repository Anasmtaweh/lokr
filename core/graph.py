import networkx as nx
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

class DependencyGraph:
    """
    Constructs a directed dependency graph of the codebase using NetworkX.
    Nodes are file paths, and edges represent import dependencies 
    (Source File -> Imported File).
    """

    def __init__(self) -> None:
        """
        Initializes an empty directed graph for neural logic.
        """
        self.graph = nx.DiGraph()

    def build_graph(self, file_paths: List[Path], parser: Any, project_root: Path) -> None:
        """
        Iterates over the given file paths, parses their AST, extracts imports,
        and builds corresponding nodes and directed edges in the graph.
        Also stores the current Git commit hash for future incremental updates.

        Args:
            file_paths (List[Path]): A list of absolute or relative file paths in the project.
            parser (Any): An instance of CodeParser to extract imports.
            project_root (Path): The root directory of the project.
        """
        # Clear existing graph
        self.graph.clear()
        # Add all valid files as nodes first
        for fp in file_paths:
            self.graph.add_node(str(fp.resolve()), node_type='file')

        # Build edges
        for fp in file_paths:
            abs_fp = fp.resolve()
            try:
                parsed_data: Dict[str, Any] = parser.parse_file(abs_fp)
                imports: List[str] = parsed_data.get("imports", [])
                import_map: Dict[str, str] = parsed_data.get("import_map", {})
                
                # Store import_map on the file node
                self.graph.nodes[str(abs_fp)]["import_map"] = import_map
                
                for imp_str in imports:
                    imported_file = self._resolve_import_to_file(imp_str, file_paths, caller_file=str(abs_fp))
                    if imported_file:
                        # Edge: Current File -> Imported File
                        self.graph.add_edge(str(abs_fp), str(imported_file), edge_type='import')

                # Build Class nodes
                classes = parsed_data.get("classes", [])
                for cls in classes:
                    cls_id = f"{abs_fp}::{cls['name']}"
                    self.graph.add_node(cls_id, node_type='class', **cls)
                    self.graph.add_edge(str(abs_fp), cls_id, edge_type='contains')

                # Build Variable nodes (BUG 1)
                variables = parsed_data.get("variables", [])
                for var in variables:
                    var_id = f"{abs_fp}::VAR::{var['name']}"
                    self.graph.add_node(var_id, node_type='variable', **var)
                    self.graph.add_edge(str(abs_fp), var_id, edge_type='contains')
                    
                # Build Config nodes
                configs = parsed_data.get("configs", [])
                for cfg in configs:
                    cfg_id = f"{abs_fp}::CONFIG::{cfg['name']}"
                    self.graph.add_node(cfg_id, node_type='config', **cfg)
                    self.graph.add_edge(str(abs_fp), cfg_id, edge_type='contains')
                    
                # Build Schema nodes (BUG 2)
                schemas = parsed_data.get("schemas", [])
                for sch in schemas:
                    sch_id = f"{abs_fp}::SCHEMA::{sch['name']}"
                    self.graph.add_node(sch_id, node_type='schema', **sch)
                    self.graph.add_edge(str(abs_fp), sch_id, edge_type='contains')

                # Build Execution nodes
                executions = parsed_data.get("executions", [])
                for idx, exe in enumerate(executions):
                    exe_id = f"{abs_fp}::{exe['name']}_{idx}"
                    self.graph.add_node(exe_id, node_type='execution', **exe)
                    self.graph.add_edge(str(abs_fp), exe_id, edge_type='contains')

                # Build Function nodes and 'contains' edges
                functions = parsed_data.get("functions", [])
                for func in functions:
                    if func.get("is_method"):
                        func_id = f"{abs_fp}::{func['parent_class']}.{func['name']}"
                        parent_id = f"{abs_fp}::{func['parent_class']}"
                    else:
                        func_id = f"{abs_fp}::{func['name']}"
                        parent_id = str(abs_fp)
                        
                    self.graph.add_node(
                        func_id,
                        node_type='function',
                        usage_count=0,
                        **func
                    )
                    self.graph.add_edge(parent_id, func_id, edge_type='contains')
            except Exception as e:
                # Log or ignore files that fail to parse
                continue

        # Establish call graph edges globally
        self._resolve_call_edges(available_files=file_paths)

        # Store the current Git state
        self.graph.graph['commit_hash'] = self._get_current_commit(project_root)
        self.graph.graph['project_root'] = str(project_root.resolve())

    def sync_with_git(self, project_root: Path, parser: Any, available_files: List[Path]) -> Dict[str, List[str]]:
        """
        Detects changes since the last build using Git and incrementally updates 
        only the affected nodes and edges.

        Args:
            project_root (Path): Root directory of the repository.
            parser (Any): CodeParser instance.
            available_files (List[Path]): List of all currently valid project files.

        Returns:
            Dict[str, List[str]]: A delta dictionary containing 'added_nodes' (new function IDs) 
                                 and 'deleted_nodes' (removed function IDs).
        """
        delta = {"added_nodes": [], "deleted_nodes": []}
        stored_hash = self.graph.graph.get('commit_hash')
        current_hash = self._get_current_commit(project_root)

        # If no hash is stored, we need to sync/save to establish the baseline
        if not stored_hash:
            if current_hash:
                self.graph.graph['commit_hash'] = current_hash
                return delta  # Return empty delta but indicates success via non-None? No, let's keep it simple.
            return delta

        # Always check for changes (committed or uncommitted) between the stored hash 
        # and the current working directory.
        try:
            result = subprocess.run(
                ["git", "diff", "--name-status", stored_hash],
                capture_output=True,
                text=True,
                cwd=str(project_root),
                check=True
            )
        except subprocess.CalledProcessError:
            return delta

        changes = result.stdout.strip().split("\n")
        if not changes or (len(changes) == 1 and not changes[0]):
            return delta

        has_changes = False
        for line in changes:
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            
            status, rel_path = parts[0], parts[1]
            abs_path = (project_root / rel_path).resolve()
            abs_path_str = str(abs_path)

            if status == 'D':
                if abs_path_str in self.graph:
                    removed = self._remove_file_and_functions(abs_path_str)
                    delta["deleted_nodes"].extend(removed)
                    has_changes = True

            elif status in ['A', 'M']:
                # For additions and modifications, re-parse the file
                # Clean up old file node and its child functions
                if abs_path_str in self.graph:
                    removed = self._remove_file_and_functions(abs_path_str)
                    delta["deleted_nodes"].extend(removed)
                
                # Ensure node exists as a 'file'
                self.graph.add_node(abs_path_str, node_type='file')
                
                try:
                    parsed_data = parser.parse_file(abs_path)
                    imports = parsed_data.get("imports", [])
                    import_map = parsed_data.get("import_map", {})
                    
                    # Store import_map on the file node
                    self.graph.nodes[abs_path_str]["import_map"] = import_map

                    for imp_str in imports:
                        imported_file = self._resolve_import_to_file(imp_str, available_files, caller_file=abs_path_str)
                        if imported_file:
                            self.graph.add_edge(abs_path_str, str(imported_file), edge_type='import')
                    
                    # Add classes
                    classes = parsed_data.get("classes", [])
                    for cls in classes:
                        cls_id = f"{abs_path_str}::{cls['name']}"
                        self.graph.add_node(cls_id, node_type='class', **cls)
                        self.graph.add_edge(abs_path_str, cls_id, edge_type='contains')
                        
                    # Add configs
                    configs = parsed_data.get("configs", [])
                    for cfg in configs:
                        cfg_id = f"{abs_path_str}::CONFIG::{cfg['name']}"
                        self.graph.add_node(cfg_id, node_type='config', **cfg)
                        self.graph.add_edge(abs_path_str, cfg_id, edge_type='contains')

                    # Add functions
                    new_function_ids = []
                    functions = parsed_data.get("functions", [])
                    for func in functions:
                        if func.get("is_method"):
                            func_id = f"{abs_path_str}::{func['parent_class']}.{func['name']}"
                            parent_id = f"{abs_path_str}::{func['parent_class']}"
                        else:
                            func_id = f"{abs_path_str}::{func['name']}"
                            parent_id = abs_path_str

                        self.graph.add_node(func_id, node_type='function', usage_count=0, **func)
                        self.graph.add_edge(parent_id, func_id, edge_type='contains')
                        new_function_ids.append(func_id)
                        delta["added_nodes"].append(func_id)
                    
                    # Add execution nodes
                    executions = parsed_data.get("executions", [])
                    for idx, exe in enumerate(executions):
                        exe_id = f"{abs_path_str}::{exe['name']}_{idx}"
                        self.graph.add_node(exe_id, node_type='execution', **exe)
                        self.graph.add_edge(abs_path_str, exe_id, edge_type='contains')
                        new_function_ids.append(exe_id)
                        delta["added_nodes"].append(exe_id)
                    
                    # Resolve calls for newly added functions
                    if new_function_ids:
                        self._resolve_call_edges(new_function_ids, available_files=available_files)

                    has_changes = True
                except Exception:
                    continue

        if has_changes:
            self.graph.graph['commit_hash'] = self._get_current_commit(project_root)
            self.graph.graph['project_root'] = str(project_root.resolve())
            
        return delta

    def increment_usage(self, node_weights: Dict[str, int]) -> None:
        """
        Increments the 'usage_count' attribute for a set of nodes.
        
        Args:
            node_weights (Dict[str, int]): Mapping of node_id to the increment value.
        """
        for node_id, weight in node_weights.items():
            if node_id in self.graph:
                current_usage = self.graph.nodes[node_id].get("usage_count", 0)
                self.graph.nodes[node_id]["usage_count"] = current_usage + weight

    def _get_current_commit(self, project_root: Path) -> str | None:
        """Retrieves the current HEAD commit hash if in a git repo."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(project_root),
                check=True
            )
            return result.stdout.strip()
        except Exception:
            return None

    def _resolve_import_to_file(self, import_str: str, available_files: List[Path], caller_file: Optional[str] = None) -> str | None:
        """
        Internal heuristic to convert an import string to a local project file path.
        Handles standard Python dotted imports and JS relative require() paths.

        Args:
            import_str (str): The raw string extracted from the AST.
            available_files (List[Path]): The list of valid project files.
            caller_file (str): Optional path of the file containing the import (for relative resolution).

        Returns:
            str | None: The absolute path string of the imported file if found, else None.
        """
        # 1. Handle common JS relative require() paths: ./utils/mailer, ../models/User
        if import_str.startswith(("./", "../")):
            if not (caller_file and available_files):
                return None
                
            try:
                caller_path = Path(caller_file)
                base_dir = caller_path.parent
                # resolve() handles the .. and . navigation
                target_path = (base_dir / import_str).resolve()
                
                # Try with extensions if missing
                search_paths = [target_path, target_path.with_suffix('.js'), target_path.with_suffix('.ts')]
                
                for sp in search_paths:
                    sp_str = str(sp)
                    if any(str(af) == sp_str for af in available_files):
                        return sp_str
                return None
            except Exception:
                return None

        # 2. Handle Python style dotted imports: core.scanner, from X import Y
        base_module = ""
        if import_str.startswith("from "):
            parts = import_str.split(" ")
            if len(parts) >= 2:
                base_module = parts[1]
        elif import_str.startswith("require("):
            # require('express') or require('../models/User')
            base_module = import_str.split("'")[1] if "'" in import_str else (import_str.split('"')[1] if '"' in import_str else "")
            # If the extracted module is a relative path, resolve it like a JS relative import
            if base_module.startswith(("./", "../")):
                if not (caller_file and available_files):
                    return None
                try:
                    caller_path = Path(caller_file)
                    base_dir = caller_path.parent
                    target_path = (base_dir / base_module).resolve()
                    search_paths = [target_path, target_path.with_suffix('.js'), target_path.with_suffix('.ts'), target_path.with_suffix('.jsx'), target_path.with_suffix('.tsx')]
                    # Also check for index.js inside a directory
                    search_paths.append(target_path / 'index.js')
                    search_paths.append(target_path / 'index.ts')
                    for sp in search_paths:
                        sp_str = str(sp)
                        if any(str(af.resolve()) == sp_str for af in available_files):
                            return sp_str
                    return None
                except Exception:
                    return None
        else:
            base_module = import_str.split(" ")[0]

        if not base_module:
            return None

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

    def save_graph(self, filepath: Path) -> None:
        """
        Serializes the NetworkX graph to a JSON file.
        
        Args:
            filepath (Path): Path to save the JSON file.
        """
        data = nx.node_link_data(self.graph)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_graph(self, filepath: Path) -> None:
        """
        Loads a NetworkX graph from a JSON file.
        
        Args:
            filepath (Path): Path to the JSON file.
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.graph = nx.node_link_graph(data)

    def _remove_file_and_functions(self, file_node_id: str) -> List[str]:
        """
        Recursively removes a file node and all its nested Classes/Methods/Functions.
        
        Args:
            file_node_id (str): The ID of the file node to remove.
        
        Returns:
            List[str]: The IDs of all removed sub-nodes (Classes and Functions).
        """
        if file_node_id not in self.graph:
            return []

        removed_ids = []
        
        def recurse_remove(node_id):
            # Find all nodes linked via 'contains' edges
            children = []
            for _, neighbor, data in self.graph.out_edges(node_id, data=True):
                if data.get('edge_type') == 'contains':
                    children.append(neighbor)
            
            # Recurse into children first
            for child in children:
                recurse_remove(child)
                if child in self.graph:
                    removed_ids.append(child)
                    self.graph.remove_node(child)

        recurse_remove(file_node_id)
        
        # Finally remove the file node itself
        if file_node_id in self.graph:
            self.graph.remove_node(file_node_id)
            
        return removed_ids

    def _resolve_call_edges(self, function_node_ids: List[str] = None, available_files: List[Path] = None) -> None:
        """
        Resolves named calls to function nodes across the entire graph.
        Also resolves 'uses' (Bug 1) and 'parent_schema_name' (Bug 2).
        
        Args:
            function_node_ids (List[str]): Optional list of specific function node IDs 
                                          to resolve calls for. If None, processes 
                                          all function nodes.
            available_files (List[Path]): List of all project files for import resolution.
        """
        if function_node_ids is None:
            # All function and execution nodes in the graph
            function_node_ids = [n for n, d in self.graph.nodes(data=True) 
                                if d.get('node_type') in ('function', 'execution')]
        
        # Build lookup maps for faster resolution
        name_map = {}
        variable_map = {}
        schema_map = {}
        
        for n, d in self.graph.nodes(data=True):
            node_type = d.get('node_type')
            if node_type in ('function', 'class'):
                name = d.get('name')
                if name:
                    if name not in name_map:
                        name_map[name] = []
                    name_map[name].append(n)
            elif node_type == 'variable':
                name = d.get('name')
                if name:
                    if name not in variable_map:
                        variable_map[name] = []
                    variable_map[name].append(n)
            elif node_type == 'schema':
                name = d.get('name')
                if name:
                    if name not in schema_map:
                        schema_map[name] = []
                    schema_map[name].append(n)
        
        # --- NEW: Cross-File Variable Resolution (BUG 1) ---
        variable_nodes = [n for n, d in self.graph.nodes(data=True) if d.get('node_type') == 'variable']
        for var_id in variable_nodes:
            # 1. Find parent file of variable
            parent_file_node = None
            preds = [p for p, _, d in self.graph.in_edges(var_id, data=True) if d.get('edge_type') == 'contains']
            if preds:
                parent_file_node = preds[0]
            
            if parent_file_node and available_files:
                import_map = self.graph.nodes[parent_file_node].get('import_map', {})
                var_name = self.graph.nodes[var_id].get('name')
                
                if var_name in import_map:
                    module_path = import_map[var_name]
                    target_file = self._resolve_import_to_file(module_path, available_files, caller_file=parent_file_node)
                    if target_file:
                        self.graph.add_edge(var_id, target_file, edge_type='resolves_to')
        
        for caller_id in function_node_ids:
            if caller_id not in self.graph:
                continue
                
            # Remove any existing 'calls' edges from this node first
            old_call_edges = [
                (u, v) for u, v, d in self.graph.out_edges(caller_id, data=True) 
                if d.get('edge_type') == 'calls'
            ]
            self.graph.remove_edges_from(old_call_edges)

            caller_data = self.graph.nodes[caller_id]
            calls_list = caller_data.get('calls', [])
            
            for callee_name in calls_list:
                # 1. Find parent file of caller
                parent_file_node = None
                curr = caller_id
                # Traverse up contains edges to find file node
                while curr:
                    preds = [p for p, _, d in self.graph.in_edges(curr, data=True) if d.get('edge_type') == 'contains']
                    if not preds:
                        break
                    p = preds[0]
                    if self.graph.nodes[p].get('node_type') == 'file':
                        parent_file_node = p
                        break
                    curr = p
                
                import_map = {}
                if parent_file_node:
                    import_map = self.graph.nodes[parent_file_node].get('import_map', {})

                # Disambiguate between scoped method calls and global functions
                is_scoped = "." in callee_name
                base_name = callee_name.split(".")[-1]
                
                # Check for precise resolution via imports
                target_file_constraint = None
                if callee_name in import_map and available_files:
                    module_path = import_map[callee_name]
                    target_file_constraint = self._resolve_import_to_file(module_path, available_files, caller_file=parent_file_node)
                elif base_name in import_map and available_files:
                    # e.g., 'u.method' -> base_name is 'method', but we need 'u' matches 'utils'
                    prefix = callee_name.split(".")[0]
                    if prefix in import_map:
                         module_path = import_map[prefix]
                         target_file_constraint = self._resolve_import_to_file(module_path, available_files, caller_file=parent_file_node)

                # Iterate through potential targets that share the base name
                for target_id in name_map.get(base_name, []):
                    if target_id == caller_id:
                        continue
                    
                    target_tail = target_id.split("::")[-1]
                    target_file = target_id.split("::")[0]
                    
                    # Apply Import-Aware Constraint
                    if target_file_constraint and target_file != target_file_constraint:
                        continue
                    
                    # Apply Same-File Locality (if not in import map)
                    if not target_file_constraint and parent_file_node and target_file != parent_file_node:
                        # If the name is in name_map for this file, prefer it
                        local_matches = [tid for tid in name_map.get(base_name, []) if tid.startswith(parent_file_node + "::")]
                        if local_matches and target_id not in local_matches:
                            continue

                    if is_scoped:
                        if target_tail == callee_name:
                            self.graph.add_edge(caller_id, target_id, edge_type='calls')
                    else:
                        if target_tail == callee_name and "." not in target_tail:
                            self.graph.add_edge(caller_id, target_id, edge_type='calls')

            # 2. Resolve 'uses' to variables -> 'depends_on' edges (BUG 1)
            uses_list = caller_data.get('uses', [])
            for use_name in uses_list:
                for target_id in variable_map.get(use_name, []):
                    # We only link variables in the SAME file by default to avoid huge fan-out
                    if parent_file_node and target_id.startswith(parent_file_node + "::"):
                        self.graph.add_edge(caller_id, target_id, edge_type='depends_on')
                        
            # 3. Resolve 'parent_schema' -> 'parent_schema' edges (BUG 2)
            parent_schema_name = caller_data.get('parent_schema_name')
            if parent_schema_name:
                for target_id in schema_map.get(parent_schema_name, []):
                    if parent_file_node and target_id.startswith(parent_file_node + "::"):
                        self.graph.add_edge(caller_id, target_id, edge_type='parent_schema')
