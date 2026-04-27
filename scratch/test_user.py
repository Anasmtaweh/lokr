import sys
from pathlib import Path
sys.path.append(str(Path('.').resolve()))
from core.parser import CodeParser

parser = CodeParser()
res = parser.parse_file(Path('scratch/user_mock.js'))
print('VARIABLES:', res.get('variables'))
print('SCHEMAS:', res.get('schemas'))
print('FUNCTIONS:', res.get('functions'))
