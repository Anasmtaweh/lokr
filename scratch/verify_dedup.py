from core.parser import CodeParser
from pathlib import Path
import json

parser = CodeParser()
test_file = Path("scratch/dedup_test.js").resolve()
result = parser.parse_file(test_file)

print(f"Results for {test_file.name}:")
print(f"Functions: {[f['name'] for f in result['functions']]}")
print(f"Variables: {[v['name'] for v in result['variables']]}")
print(f"Classes: {[c['name'] for c in result['classes']]}")

# Verification logic
assert "signup" in [f['name'] for f in result['functions']], "signup should be a function"
assert "signup" not in [v['name'] for v in result['variables']], "signup should NOT be a variable (ghost)"
assert "myVar" in [v['name'] for v in result['variables']], "myVar should be a variable"
print("\n[SUCCESS] Deduplication logic verified.")
