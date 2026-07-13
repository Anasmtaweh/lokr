import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.vector_db import CodebaseVectorDB

db = CodebaseVectorDB()

print("Querying for 'express'...")
results = db.search("express", n_results=5)
print("Hits for 'express':")
for i, res in enumerate(results):
    print(f"[{i}] {res['node_id']} - {res['document'][:100]}")

print("\nQuerying for 'AWS S3'...")
results = db.search("AWS S3", n_results=5)
print("Hits for 'AWS S3':")
for i, res in enumerate(results):
    print(f"[{i}] {res['node_id']} - {res['document'][:100]}")
