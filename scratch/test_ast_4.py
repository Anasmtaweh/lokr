import sys
from pathlib import Path
sys.path.append(str(Path('.').resolve()))
from core.parser import CodeParser

parser = CodeParser()

def extract_top(node, code, result):
    print("extract_top called for", node.child_by_field_name('name').text)
    parser.__class__._extract_top_level_variable(parser, node, code, result)

parser._extract_top_level_variable = extract_top

res = parser.parse_file(Path('scratch/test.js'))
print('VARIABLES:', res.get('variables'))
