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
                "raw_text": code_text
            }

        # AST Parsing for supported files
        self.parser.language = self.languages[ext]
        tree = self.parser.parse(code_bytes)
        root_node = tree.root_node

        result: Dict[str, Any] = {
            "file_path": str(filepath),
            "imports": [],
            "classes": [],
            "functions": []
        }

        self._walk_ast(root_node, code_bytes, result)
        return result

    def _walk_ast(self, node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any]) -> None:
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

        # -- Functions --
        elif node_type in ['function_definition', 'function_declaration', 'method_definition', 'arrow_function']:
            func_info = self._extract_function(node, code_bytes)
            if func_info:
                result["functions"].append(func_info)

        # Recurse into children
        for child in node.children:
            self._walk_ast(child, code_bytes, result)

    def _extract_import(self, node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any]) -> None:
        """Parses standard import statements."""
        for child in node.children:
            if child.type == 'dotted_name' or child.type == 'aliased_import':
                module_name = child.text.decode('utf-8')
                result["imports"].append(module_name)

    def _extract_from_import(self, node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any]) -> None:
        """Parses `from X import Y` statements."""
        module_name = ""
        for child in node.children:
            if child.type == 'dotted_name':
                module_name = child.text.decode('utf-8')
                break
        
        import_names = []
        for child in node.children:
            if child.type == 'dotted_name' and child.text.decode('utf-8') == module_name:
                continue
            if child.type == 'aliased_import' or child.type == 'dotted_name':
                import_names.append(child.text.decode('utf-8'))
        
        if module_name:
             full_import = f"from {module_name} import {', '.join(import_names)}" if import_names else f"from {module_name} import *"
             result["imports"].append(full_import)

    def _extract_generic_import(self, node: tree_sitter.Node, code_bytes: bytes, result: Dict[str, Any]) -> None:
        """Fallback for JS 'require_call' and PHP 'namespace_use_declaration'"""
        imp_text = node.text.decode('utf-8').strip()
        # Cap length to avoid accidentally indexing huge blocks of code
        if len(imp_text) < 150:
            result["imports"].append(imp_text)

    def _extract_class(self, node: tree_sitter.Node, code_bytes: bytes) -> Optional[Dict[str, Any]]:
        """Extracts class names across multiple ASTs."""
        name_node = node.child_by_field_name('name')
        if not name_node:
            return None
        
        return {
            "name": name_node.text.decode('utf-8')
        }

    def _extract_function(self, node: tree_sitter.Node, code_bytes: bytes) -> Optional[Dict[str, Any]]:
        """Extracts function names and parameters across multiple ASTs."""
        name_node = node.child_by_field_name('name')
        if not name_node:
            return None
            
        func_name = name_node.text.decode('utf-8')
        parameters: List[str] = []
        docstring: Optional[str] = None

        # Extract parameters
        params_node = node.child_by_field_name('parameters')
        if params_node:
            # Exclude punctuation tokens like '(', ')', '{', '}', ',' across languages
            for child in params_node.children:
                if child.type not in ['(', ')', '{', '}', ',']:
                    parameters.append(child.text.decode('utf-8'))

        # Standard docstring extraction for python (usually body -> expression_statement -> string)
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
            "name": func_name,
            "parameters": parameters,
            "docstring": docstring
        }
