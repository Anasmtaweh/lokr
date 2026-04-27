import sys
import networkx as nx
from pathlib import Path
sys.path.append(str(Path('.').resolve()))
from core.parser import CodeParser
from core.graph import DependencyGraph
from core.indexer import Indexer
from data.vector_db import CodebaseVectorDB

# 1. Parse and Build Graph
parser = CodeParser()
graph = DependencyGraph()
graph.build_graph([Path('scratch/test.js')], parser, Path('.'))

# 2. Init DB and Index
import time
db = CodebaseVectorDB(Path(f'.lokr_test_db_{int(time.time())}'))
# clear old nodes
indexer = Indexer(db)
indexer.index_nodes(graph)

# 3. Search
print("\n--- Testing Vector Embedding ---")
res = db.search("mongoose schema for user email", n_results=2)
for hit in res:
    print(f"Hit Node: {hit['node_id']} | Score: {hit.get('score')}")

res = db.search("how does the system send an email via smtp?", n_results=2)
for hit in res:
    print(f"Hit Node: {hit['node_id']} | Score: {hit.get('score')}")
