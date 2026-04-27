import sys
from pathlib import Path
sys.path.append(str(Path('.').resolve()))
from core.parser import CodeParser
from core.graph import DependencyGraph
from core.retriever import Retriever
from data.vector_db import CodebaseVectorDB

# 1. Setup Mock Project
# We assume scratch/user_mock.js (simulating models/User.js) and scratch/auth_mock.js
# But resolves_to logic expects the file paths to match the import string.
# Let's create a real structure in scratch:
# scratch/models/User.js
# scratch/auth.js

models_dir = Path('scratch/models')
models_dir.mkdir(exist_ok=True)

with open('scratch/models/User.js', 'w') as f:
    f.write("""
const mongoose = require('mongoose');
const userSchema = new mongoose.Schema({ email: String });
userSchema.pre('save', function(next) { console.log('hashing...'); next(); });
module.exports = mongoose.model('User', userSchema);
""")

with open('scratch/auth.js', 'w') as f:
    f.write("""
const User = require('./models/User');
const signup = async (req, res) => {
    const user = new User(req.body);
    await user.save();
};
""")

# 2. Build Graph
parser = CodeParser()
graph = DependencyGraph()
files = [Path('scratch/models/User.js').resolve(), Path('scratch/auth.js').resolve()]
graph.build_graph(files, parser, Path('scratch').resolve())

# 3. Check for resolves_to edge
var_id = str(Path('scratch/auth.js').resolve()) + "::VAR::User"
print(f"Checking var node: {var_id}")
if var_id in graph.graph:
    edges = list(graph.graph.out_edges(var_id, data=True))
    print("Edges from VAR::User:", edges)
else:
    print("VAR::User not found in graph!")

# 4. Check for expansion
print("\n--- Expansion Test (signup -> User -> File -> Schema) ---")
signup_id = str(Path('scratch/auth.js').resolve()) + "::signup"

# Let's verify the actual retriever.search_and_expand code works
# Since we haven't indexed, we'll mock the 'initial_hits' by patching search temporarily or just checking search_and_expand source
# Actually, I'll just check if the logic I added to retriever.py is correct by running it.
# We don't need a DB if we avoid the search step.

centers = {signup_id}
# Manual 1-hop expansion simulation using the retriever's logic
context_ids = set(centers)
for node_id in centers:
    # Succs
    for _, neighbor, data in graph.graph.out_edges(node_id, data=True):
        if data.get('edge_type') in ('calls', 'depends_on', 'parent_schema', 'resolves_to'):
            context_ids.add(neighbor)
            if data.get('edge_type') == 'resolves_to':
                for _, s_n, s_d in graph.graph.out_edges(neighbor, data=True):
                    if s_d.get('edge_type') == 'contains':
                        context_ids.add(s_n)
    # Preds
    for neighbor, _, data in graph.graph.in_edges(node_id, data=True):
        if data.get('edge_type') in ('calls', 'depends_on', 'parent_schema'):
            context_ids.add(neighbor)

print("Expanded Nodes:", [n.split('/')[-1] for n in context_ids])
expected_schema = "SCHEMA::userSchema"
if any(expected_schema in n for n in context_ids):
    print(f"✅ Success: Found {expected_schema} from signup!")

print("\n--- Expansion Test (Backward: Schema -> Hooks) ---")
schema_id = str(Path('scratch/models/User.js').resolve()) + "::SCHEMA::userSchema"
centers = {schema_id}
context_ids = set(centers)
for node_id in centers:
    # Succs
    for _, neighbor, data in graph.graph.out_edges(node_id, data=True):
        if data.get('edge_type') in ('calls', 'depends_on', 'parent_schema', 'resolves_to'):
            context_ids.add(neighbor)
    # Preds (to catch parent_schema edges pointing AT the schema)
    for neighbor, _, data in graph.graph.in_edges(node_id, data=True):
        if data.get('edge_type') in ('calls', 'depends_on', 'parent_schema'):
            context_ids.add(neighbor)

print("Expanded Nodes from Schema:", [n.split('/')[-1] for n in context_ids])
expected_hook = "userSchema.pre(save)"
if any(expected_hook in n for n in context_ids):
    print(f"✅ Success: Found {expected_hook} from Schema!")
