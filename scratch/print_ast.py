import sys
from pathlib import Path
sys.path.append(str(Path('.').resolve()))
from core.parser import CodeParser
import tree_sitter

parser = CodeParser()
parser.parser.language = parser.languages['.js']
with open('scratch/test.js', 'rb') as f:
    tree = parser.parser.parse(f.read())

def print_tree(node, depth=0):
    print("  " * depth + str(node.type))
    for child in node.children:
        print_tree(child, depth + 1)

print_tree(tree.root_node)
