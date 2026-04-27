import sys
from pathlib import Path
sys.path.append(str(Path('.').resolve()))
from core.parser import CodeParser

code = """
let transporter;
if (true) {
    transporter = nodemailer.createTransport({ service: 'gmail' });
}
"""

parser = CodeParser()
# Mock parse_file logic
from tree_sitter import Language, Parser
import tree_sitter_javascript as tsjs
JS_LANGUAGE = Language(tsjs.language())
ts_parser = Parser(JS_LANGUAGE)
tree = ts_parser.parse(code.encode('utf-8'))

result = {
    "imports": [],
    "import_map": {},
    "classes": [],
    "functions": [],
    "variables": [],
    "schemas": []
}

parser._walk_ast(tree.root_node, code.encode('utf-8'), result)

print("VARIABLES EXTRACTED:")
for v in result["variables"]:
    print(f" - {v['name']} (Lines {v['lineno']}-{v['end_lineno']})")
