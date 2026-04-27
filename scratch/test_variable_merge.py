import sys
from pathlib import Path
sys.path.append(str(Path('.').resolve()))
from core.parser import CodeParser

code = """
let transporter;
if (config.EMAIL_USER) {
    transporter = nodemailer.createTransport({ service: 'gmail' });
} else {
    transporter = null;
}
"""

parser = CodeParser()
# Mock parse_file behavior for the test
import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser
JS_LANGUAGE = Language(tsjs.language())
ts_parser = Parser(JS_LANGUAGE)
tree = ts_parser.parse(code.encode('utf-8'))

result = {
    "file_path": "mock.js",
    "imports": [],
    "import_map": {},
    "classes": [],
    "functions": [],
    "variables": [],
    "schemas": [],
    "variable_map": {}
}

parser._walk_ast(tree.root_node, code.encode('utf-8'), result)

# Finalize map like parse_file does
for var_name, var_data in result.pop("variable_map", {}).items():
    result["variables"].append(var_data)

print("VARIABLES EXTRACTED:")
for v in result["variables"]:
    print(f"Name: {v['name']}")
    print(f"Source Code:\n{v['source_code']}")
    print("-" * 20)
