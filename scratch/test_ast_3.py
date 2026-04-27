import sys
from pathlib import Path
sys.path.append(str(Path('.').resolve()))
from core.parser import CodeParser

parser = CodeParser()
parser.parser.language = parser.languages['.js']
with open('scratch/test.js', 'rb') as f:
    tree = parser.parser.parse(f.read())

for child in tree.root_node.children:
    if child.type == 'lexical_declaration':
        var_decl = child.children[1]
        print("var_decl:", var_decl.type)
        print("name node:", var_decl.child_by_field_name('name'))
        print("value node:", var_decl.child_by_field_name('value'))
        print("children:", [c.type for c in var_decl.children])
