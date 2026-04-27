import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import tree_sitter

class CodeParser:
    """
    AST Parser for multiple source languages using modern tree-sitter API.
    Extracts high-level semantic elements like imports, classes, and functions.
    Supports Python, JavaScript, TypeScript, HTML, CSS, and PHP.
    """

    def __init__(self) -> None:
        """
        Initializes the Tree-sitter parsers dynamically for supported languages.
        """
        self.languages = {}

        # Python
        try:
            import tree_sitter_python as tspython
            self.languages[".py"] = tree_sitter.Language(tspython.language())
        except ImportError:
            pass

        # JavaScript
        try:
            import tree_sitter_javascript as tsjavascript
            self.languages[".js"] = tree_sitter.Language(tsjavascript.language())
            self.languages[".jsx"] = tree_sitter.Language(tsjavascript.language())
        except ImportError:
            pass

        # TypeScript
        try:
            import tree_sitter_typescript as tstypescript
            self.languages[".ts"] = tree_sitter.Language(tstypescript.language_typescript())
            self.languages[".tsx"] = tree_sitter.Language(tstypescript.language_tsx())
        except ImportError:
            pass

        # HTML
        try:
            import tree_sitter_html as tshtml
            self.languages[".html"] = tree_sitter.Language(tshtml.language())
            self.languages[".htm"] = tree_sitter.Language(tshtml.language())
        except ImportError:
            pass

        # CSS
        try:
            import tree_sitter_css as tscss
            self.languages[".css"] = tree_sitter.Language(tscss.language())
        except ImportError:
            pass

        # PHP
        try:
            import tree_sitter_php as tsphp
            self.languages[".php"] = tree_sitter.Language(tsphp.language_php())
            self.languages[".php5"] = tree_sitter.Language(tsphp.language_php())
            self.languages[".phtml"] = tree_sitter.Language(tsphp.language_php())
        except ImportError:
            pass

        self.parser = tree_sitter.Parser()

    def parse_file(self, filepath: Path) -> Dict[str, Any]:
        """
        Parses a target source file dynamically based on its extension.

        Args:
            filepath (Path): The absolute path to the file.

        Returns:
            Dict[str, Any]: A JSON-serializable structured dictionary containing AST elements.
        """
        filepath = Path(filepath).resolve()
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                code_text = f.read()
            code_bytes = code_text.encode('utf-8')
        except Exception as e:
            raise RuntimeError(f"Failed to read file {filepath}: {e}")

        ext = filepath.suffix.lower()

        # Crucial Fallback: Raw text for unsupported files
        if ext not in self.languages:
            return {
                "file_path": str(filepath),
                "imports": [],
                "classes": [],
                "functions": [],
                "variables": [],
                "schemas": [],
                "raw_text": code_text
            }

        # AST Parsing for supported files
        self.parser.language = self.languages[ext]
        tree = self.parser.parse(code_bytes)
        root_node = tree.root_node

        result: Dict[str, Any] = {
            "file_path": str(filepath),
            "imports": [],
            "import_map": {},
            "classes": [],
            "functions": [],
            "variables": [],
            "schemas": [],
            "variable_map": {} # Temporary map for merging re-assignments
        }

        self._walk_ast(root_node, code_bytes, result)
        
        # Finalize merged variables from map into the result list
        for var_name, var_data in result.pop("variable_map", {}).items():
            result["variables"].append(var_data)
            
        # Task 16: Deduplicate nodes (Arrows, Ghost Variables)
        self._deduplicate_nodes(result)
            
        return result

    def _deduplicate_nodes(self, result: Dict[str, Any]) -> None:
        """
        Eliminates duplicate 'ghost nodes' where a variable name overlaps 
        with a function or class name (common in JS arrow function declarations).
        """
        function_names = {f["name"] for f in result.get("functions", [])}
        class_names = {c["name"] for c in result.get("classes", [])}
        semantic_names = function_names.union(class_names)
        
        # Filter variables: Keep only those that don't overlap with a semantic node
        filtered_variables = [
            v for v in result.get("variables", [])
            if v["name"] not in semantic_names
        ]
        result["variables"] = filtered_variables

    def _walk_ast(self, node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any], current_class: Optional[str] = None) -> None:
        """
        Recursively walks the AST and populates the result dictionary 
        across multiple languages for imports, classes, and functions.
        """
        node_type = node.type

        # -- Imports --
        if node_type == 'import_statement':
            self._extract_import(node, code_bytes, result)
        elif node_type == 'import_from_statement':
            self._extract_from_import(node, code_bytes, result)
        elif node_type in ['require_call', 'namespace_use_declaration']:
            self._extract_generic_import(node, code_bytes, result)

        # -- Classes --
        elif node_type in ['class_definition', 'class_declaration']:
            class_info = self._extract_class(node, code_bytes)
            if class_info:
                result["classes"].append(class_info)
                # Walk children with this class as context
                body_node = node.child_by_field_name('body')
                if body_node:
                    for child in body_node.children:
                        self._walk_ast(child, code_bytes, result, current_class=class_info["name"])
                return # Skip standard recursion for children already handled above

        # -- Functions --
        elif node_type in ['function_definition', 'function_declaration', 'method_definition', 'arrow_function', 'async_function_definition', 'async_method_definition']:
            func_info = self._extract_function(node, code_bytes, parent_class=current_class)
            if func_info:
                result["functions"].append(func_info)

        # -- JavaScript Specific Patterns (Anonymous handlers, Routes, require) --
        elif node_type == 'call_expression':
            # Handle Route handlers: router.post('/signup', (req, res) => { ... })
            self._extract_js_route_handler(node, code_bytes, result)
            # require() as import
            func_node = node.child_by_field_name('function')
            if func_node and func_node.text == b'require':
                self._extract_js_require(node, code_bytes, result)
                
            # BUG 2: Mongoose Schema Detachment 
            self._extract_mongoose_hook(node, code_bytes, result)
        
        elif node_type == 'variable_declarator':
            # Handle Assigned functions: const signup = (req, res) => { ... }
            self._handle_js_variable_assignment(node, code_bytes, result)
            # Track top level variables
            if not current_class and not self._is_inside_function(node):
                self._extract_top_level_variable(node, code_bytes, result)

        elif node_type == 'assignment_expression':
            # Track top level assignments (transporter = ...)
            if not current_class and not self._is_inside_function(node):
                self._extract_top_level_variable(node, code_bytes, result)
        
        elif node_type == 'expression_statement':
            # Handle mongoose schemas if they are calls
            expr = node.child_by_field_name('expression')
            if expr and expr.type == 'new_expression':
                 self._extract_mongoose_schema(node, expr, code_bytes, result)

        # Recurse into children
        for child in node.children:
            self._walk_ast(child, code_bytes, result, current_class=current_class)

    def _extract_import(self, node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any]) -> None:
        """Parses standard import statements and populates the import map."""
        for child in node.children:
            if child.type == 'dotted_name':
                module_name = child.text.decode('utf-8')
                result["imports"].append(module_name)
                # 'import core.graph' -> {'graph': 'core.graph'}
                local_name = module_name.split('.')[-1]
                result["import_map"][local_name] = module_name
            elif child.type == 'aliased_import':
                # 'import core.graph as cg'
                name_node = child.child_by_field_name('name')
                alias_node = child.child_by_field_name('alias')
                if name_node and alias_node:
                    module_name = name_node.text.decode('utf-8')
                    alias_name = alias_node.text.decode('utf-8')
                    result["imports"].append(module_name)
                    result["import_map"][alias_name] = module_name

    def _extract_from_import(self, node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any]) -> None:
        """Parses `from X import Y` statements and populates the import map."""
        module_name = ""
        for child in node.children:
            if child.type == 'dotted_name':
                module_name = child.text.decode('utf-8')
                break
        
        import_names = []
        for child in node.children:
            node_type = child.type
            if node_type == 'dotted_name' and child.text.decode('utf-8') == module_name:
                continue
            
            if node_type == 'dotted_name':
                name = child.text.decode('utf-8')
                import_names.append(name)
                if module_name:
                    result["import_map"][name] = f"{module_name}.{name}"
            elif node_type == 'aliased_import':
                name_node = child.child_by_field_name('name')
                alias_node = child.child_by_field_name('alias')
                if name_node and alias_node:
                    name = name_node.text.decode('utf-8')
                    alias = alias_node.text.decode('utf-8')
                    import_names.append(f"{name} as {alias}")
                    if module_name:
                        result["import_map"][alias] = f"{module_name}.{name}"
        
        if module_name:
             full_import = f"from {module_name} import {', '.join(import_names)}" if import_names else f"from {module_name} import *"
             result["imports"].append(full_import)

    def _extract_generic_import(self, node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any]) -> None:
        """Fallback for JS 'require_call' and PHP 'namespace_use_declaration'"""
        imp_text = node.text.decode('utf-8').strip()
        # Cap length to avoid accidentally indexing huge blocks of code
        if len(imp_text) < 150:
            result["imports"].append(imp_text)

    def _extract_js_require(self, node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any]) -> None:
        """Extracts JS require() calls and populates the import map."""
        args = node.child_by_field_name('arguments')
        if not args or len(args.children) < 2:
            return
        
        # require('module')
        module_node = args.children[1] # [0] is '(', [1] is string
        if module_node.type == 'string':
            module_name = module_node.text.decode('utf-8').strip("'\"")
            result["imports"].append(f"require('{module_name}')")
            
            # If this require is part of a variable declaration, map the variable to the module
            # const User = require('./models/User')
            parent = node.parent
            if parent and parent.type == 'variable_declarator':
                name_node = parent.child_by_field_name('name')
                if name_node:
                    alias = name_node.text.decode('utf-8')
                    result["import_map"][alias] = module_name

    def _extract_js_route_handler(self, node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any]) -> None:
        """Detects Express.js route handlers and extracts anonymous closures as named nodes."""
        func_node = node.child_by_field_name('function')
        if not (func_node and func_node.type == 'member_expression'):
            return
            
        obj = func_node.child_by_field_name('object')
        prop = func_node.child_by_field_name('property')
        if not (obj and prop):
            return
            
        obj_text = obj.text.decode('utf-8')
        prop_text = prop.text.decode('utf-8')
        
        # Common route methods
        if obj_text in ['router', 'app'] and prop_text in ['get', 'post', 'put', 'delete', 'patch', 'use']:
            args = node.child_by_field_name('arguments')
            if not args:
                return
            
            # Identify the path and the handler
            path = "unknown"
            handler_node = None
            
            for arg in args.children:
                if arg.type == 'string':
                    path = arg.text.decode('utf-8').strip("'\"")
                elif arg.type in ['arrow_function', 'function_expression']:
                    handler_node = arg
            
            if handler_node:
                synthetic_name = f"{prop_text.upper()}::{path}"
                func_info = self._extract_function(handler_node, code_bytes, manual_name=synthetic_name)
                if func_info:
                    result["functions"].append(func_info)

    def _handle_js_variable_assignment(self, node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any]) -> None:
        """Detects functional assignments in JS like 'const myFunc = () => { ... }'"""
        name_node = node.child_by_field_name('name')
        value_node = node.child_by_field_name('value')
        
        if name_node and value_node and value_node.type in ['arrow_function', 'function_expression']:
            func_name = name_node.text.decode('utf-8')
            func_info = self._extract_function(value_node, code_bytes, manual_name=func_name)
            if func_info:
                result["functions"].append(func_info)

    def _is_inside_function(self, node: tree_sitter.Node) -> bool:
        """Helper to walk up tree to see if node is inside a function"""
        curr = node.parent
        while curr:
            if curr.type in ['function_definition', 'function_declaration', 'arrow_function', 'function_expression', 'method_definition']:
                return True
            curr = curr.parent
        return False

    def _extract_top_level_variable(self, node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any]) -> None:
        """Extracts significant top-level variables and assignments, merging re-assignments (BUG 1 fix)."""
        name_node = None
        if node.type == 'variable_declarator':
            name_node = node.child_by_field_name('name')
        elif node.type == 'assignment_expression':
            name_node = node.child_by_field_name('left')
            
        if name_node and name_node.type in ('identifier', 'property_identifier'):
            var_name = name_node.text.decode('utf-8')
            # Extract parent statement if possible for better context
            parent = node.parent
            target_node = node
            if parent and parent.type in ('lexical_declaration', 'variable_declaration', 'expression_statement'):
                target_node = parent
                
            start_row, start_col = target_node.start_point
            end_row, end_col = target_node.end_point
            
            # Fetch raw snippet for this specific assignment
            lines = code_bytes.decode('utf-8', errors='ignore').splitlines()
            snippet = "\n".join(lines[start_row:end_row + 1])
            
            if var_name in result["variable_map"]:
                # Concatenate re-assignments (Fixing the OVERWRITE BUG)
                prev_entry = result["variable_map"][var_name]
                if snippet not in prev_entry["source_code"]:
                    prev_entry["source_code"] += f"\n// Re-assignment:\n{snippet}"
            else:
                result["variable_map"][var_name] = {
                    "name": var_name,
                    "source_code": snippet,
                    "lineno": start_row + 1,
                    "end_lineno": end_row + 1
                }

    def _extract_mongoose_schema(self, node: tree_sitter.Node, new_expr_node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any]) -> None:
        """Extracts new mongoose.Schema definitions (BUG 2 fix)."""
        clazz_node = new_expr_node.child_by_field_name('constructor')
        if not clazz_node:
            for child in new_expr_node.children:
                if child.type in ['identifier', 'member_expression']:
                    clazz_node = child
                    break
        if clazz_node:
            class_text = clazz_node.text.decode('utf-8')
            if 'Schema' in class_text:
                name_node = node.child_by_field_name('name')
                if name_node:
                    schema_name = name_node.text.decode('utf-8')
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    result["schemas"].append({
                        "name": schema_name,
                        "lineno": start_line,
                        "end_lineno": end_line
                    })

    def _extract_mongoose_hook(self, node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any]) -> None:
        """Extracts Mongoose schema hooks/methods into functions linked to parent schemas (BUG 2 fix)."""
        func_node = node.child_by_field_name('function')
        if not (func_node and func_node.type == 'member_expression'): return
        obj = func_node.child_by_field_name('object')
        prop = func_node.child_by_field_name('property')
        if not (obj and prop): return
        obj_text = obj.text.decode('utf-8')
        prop_text = prop.text.decode('utf-8')
        if prop_text in ['pre', 'post', 'methods', 'statics']:
            args = node.child_by_field_name('arguments')
            if not args: return
            hook_name = ""
            handler_node = None
            for arg in args.children:
                if arg.type == 'string': hook_name = arg.text.decode('utf-8').strip("'\"")
                elif arg.type in ['arrow_function', 'function_expression']: handler_node = arg
            if handler_node:
                synthetic_name = f"{obj_text}.{prop_text}({hook_name})"
                func_info = self._extract_function(handler_node, code_bytes, manual_name=synthetic_name)
                if func_info:
                    func_info["parent_schema_name"] = obj_text
                    result["functions"].append(func_info)

    def _extract_class(self, node: tree_sitter.Node, code_bytes: bytes) -> Optional[Dict[str, Any]]:
        """Extracts class names, location, and docstrings."""
        name_node = node.child_by_field_name('name')
        if not name_node:
            return None
        
        class_name = name_node.text.decode('utf-8')
        docstring: Optional[str] = None

        # Python Docstring Extraction
        body_node = node.child_by_field_name('body')
        if body_node and body_node.type == 'block':
            if len(body_node.children) > 0:
                first_stmt = body_node.children[0]
                if first_stmt.type == 'expression_statement':
                    str_node = first_stmt.child(0)
                    if str_node and str_node.type == 'string':
                        doc_text = str_node.text.decode('utf-8')
                        docstring = doc_text.strip('''"'{}\\''')

        return {
            "name": class_name,
            "docstring": docstring,
            "lineno": node.start_point[0] + 1,
            "end_lineno": node.end_point[0] + 1
        }

    def _extract_function(self, node: tree_sitter.Node, code_bytes: bytes, parent_class: Optional[str] = None, manual_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Extracts function names, parameters, location, and signatures."""
        name_node = node.child_by_field_name('name')
        if not name_node and not manual_name:
            return None
            
        func_name = manual_name if manual_name else name_node.text.decode('utf-8')
        parameters: List[str] = []
        docstring: Optional[str] = None

        # Extract parameters and local type hints
        params_node = node.child_by_field_name('parameters')
        local_type_map: Dict[str, str] = {}
        
        if params_node:
            for child in params_node.children:
                if child.type not in ['(', ')', '{', '}', ',']:
                    parameters.append(child.text.decode('utf-8'))
                
                # Check for type hints
                if child.type == 'typed_parameter':
                    id_node = None
                    type_node = None
                    # First identifier is variable name, 'type' contains the annotation
                    for subchild in child.children:
                        if subchild.type == 'identifier' and not id_node:
                            id_node = subchild
                        elif subchild.type == 'type':
                            type_node = subchild
                    
                    if id_node and type_node:
                        id_name = id_node.text.decode('utf-8')
                        type_name = type_node.text.decode('utf-8')
                        local_type_map[id_name] = type_name

        # Standard docstring extraction for python
        body_node = node.child_by_field_name('body')
        if body_node and body_node.type == 'block':
            if len(body_node.children) > 0:
                first_stmt = body_node.children[0]
                if first_stmt.type == 'expression_statement':
                    str_node = first_stmt.child(0)
                    if str_node and str_node.type == 'string':
                        doc_text = str_node.text.decode('utf-8')
                        docstring = doc_text.strip('''"'{}\\''')

        # Location
        start_line = node.start_point[0] + 1  # 1-indexed
        end_line = node.end_point[0] + 1

        # Signature
        signature = f"{func_name}({', '.join(parameters)})"

        # Extract calls within function body
        calls_set: set[str] = set()
        if body_node:
            self._extract_calls(body_node, calls_set, current_class=parent_class, local_type_map=local_type_map)

        # Identifiers used in the function (BUG 1 fix)
        uses_set: set[str] = set()
        if body_node:
            self._extract_uses(body_node, uses_set)

        return {
            "name": func_name,
            "parent_class": parent_class,
            "is_method": parent_class is not None,
            "parameters": parameters,
            "signature": signature,
            "docstring": docstring,
            "lineno": start_line,
            "end_lineno": end_line,
            "calls": list(calls_set),
            "uses": list(uses_set)
        }

    def _extract_uses(self, node: tree_sitter.Node, uses_set: set[str]) -> None:
        """Recursively finds all unresolved identifiers to link variables."""
        if node.type == 'identifier':
            # Avoid property identifiers (e.g. obj.PROPERTY) being marked as uses
            parent = node.parent
            if parent and parent.type == 'member_expression':
                if parent.child_by_field_name('property') == node:
                    pass
                else:
                    uses_set.add(node.text.decode('utf-8'))
            else:
                uses_set.add(node.text.decode('utf-8'))
                
        for child in node.children:
            self._extract_uses(child, uses_set)


    def _extract_calls(self, node: tree_sitter.Node, calls_set: set[str], current_class: Optional[str] = None, local_type_map: Optional[Dict[str, str]] = None) -> None:
        """
        Recursively finds all function and method calls in a given AST subtree.
        If a call is to 'self'/'this', it is recorded as 'Class.method'.
        If a call is to a typed variable, it uses the type hint (e.g., 'Type.method').
        """
        if local_type_map is None:
            local_type_map = {}
            
        node_type = node.type

        # Generic call detection (covers Python 'call', JS 'call_expression', etc.)
        if node_type in ['call', 'call_expression', 'function_call_expression']:
            func_node = node.child_by_field_name('function')
            if func_node:
                # Direct call: helper()
                if func_node.type == 'identifier':
                    call_name = func_node.text.decode('utf-8')
                    # Task 16: Clean VAR:: prefix if it somehow leaked into AST (e.g. from previous graph states)
                    if call_name.startswith("VAR::"):
                        call_name = call_name[5:]
                    calls_set.add(call_name)
                # Method call: obj.method()
                elif func_node.type in ['attribute', 'member_expression']:
                    # In tree-sitter-python, attribute has 'object' and 'attribute' fields
                    # In tree-sitter-javascript, member_expression has 'object' and 'property' fields
                    obj_node = func_node.child_by_field_name('object')
                    attr_node = func_node.child_by_field_name('attribute') or func_node.child_by_field_name('property')
                    
                    if obj_node and attr_node:
                        obj_text = obj_node.text.decode('utf-8')
                        attr_text = attr_node.text.decode('utf-8')
                        
                        # Disambiguate self/this calls if inside a class
                        if current_class and obj_text in ['self', 'this']:
                            calls_set.add(f"{current_class}.{attr_text}")
                        elif obj_text in local_type_map:
                            # Apply Type Hint based resolution
                            calls_set.add(f"{local_type_map[obj_text]}.{attr_text}")
                        else:
                            # Standard method call: obj.save() -> just record 'save' for now
                            calls_set.add(attr_text)
                    elif attr_node:
                        # Fallback for unexpected AST structures missing 'object'
                        calls_set.add(attr_node.text.decode('utf-8'))

        # Recurse
        for child in node.children:
            self._extract_calls(child, calls_set, current_class=current_class, local_type_map=local_type_map)
