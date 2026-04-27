import sys
from pathlib import Path
sys.path.append(str(Path('.').resolve()))
from data.vector_db import CodebaseVectorDB

db = CodebaseVectorDB(Path('data/vector_store'))
print("Total documents in Chroma DB:", db.collection.count())
res = db.search("password meets complexity requirements and is hashed before being saved", n_results=5)
print("\nSearch results for 'password meets complexity...':")
for hit in res:
    print(f"Hit Node: {hit.get('node_id')} | Score: {hit.get('score')}")
    # print code snippet if available
    d = db.collection.get(ids=[hit['node_id']])
    print(f"  Type: {d['metadatas'][0].get('node_type', 'N/A')}")
