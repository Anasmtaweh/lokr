import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser

code = """
let transporter;
if (true) {
    transporter = nodemailer.createTransport({ service: 'gmail' });
}
"""

JS_LANGUAGE = Language(tsjs.language())
parser = Parser(JS_LANGUAGE)
tree = parser.parse(code.encode('utf-8'))

def print_tree(node, depth=0):
    print("  " * depth + f"{node.type} ({node.start_point}-{node.end_point})")
    for child in node.children:
        print_tree(child, depth + 1)

print_tree(tree.root_node)
