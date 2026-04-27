import sys
from pathlib import Path
sys.path.append(str(Path('.').resolve()))
from core.parser import CodeParser

parser = CodeParser()
res = parser.parse_file(Path('scratch/test.js'))
print('VARIABLES:', res.get('variables'))
print('SCHEMAS:', res.get('schemas'))
print('FUNCTIONS:', res.get('functions'))

# Also let's print if variables/schemas logic is reached
def mock_extract(node, code_bytes, result):
    print("Found variable_declarator:", node.text)

parser._extract_top_level_variable = mock_extract

