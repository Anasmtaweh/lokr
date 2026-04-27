import sys
from pathlib import Path
sys.path.append(str(Path('.').resolve()))
from data.vector_db import CodebaseVectorDB

db = CodebaseVectorDB(Path('.lokr/vector_db'))
print("Total documents in Chroma DB:", db.collection.count())
res = db.search("password meets complexity requirements and is hashed before being saved", n_results=5)
for hit in res:
    print(f"Hit Node: {hit['node_id']} | Score: {hit.get('score')}")
