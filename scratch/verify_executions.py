import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner import CodeScanner
from core.parser import CodeParser
from core.graph import DependencyGraph

def main():
    target_dir = Path("/home/anas/MyProjects/pet-ai-project")
    scanner = CodeScanner(target_dir=target_dir)
    project_files = list(scanner.get_files())
    
    code_parser = CodeParser()
    dep_graph = DependencyGraph()
    
    print("Building graph...")
    dep_graph.build_graph(file_paths=project_files, parser=code_parser, project_root=target_dir)
    
    execution_nodes = [n for n, d in dep_graph.graph.nodes(data=True) if d.get('node_type') == 'execution']
    
    print(f"Found {len(execution_nodes)} execution nodes:")
    for nid in execution_nodes:
        data = dep_graph.graph.nodes[nid]
        print(f" - {data.get('name')}: {data.get('source_code')[:100].strip()}...")
        print(f"   Calls: {data.get('calls')}")
        edges = list(dep_graph.graph.edges(nid))
        print(f"   Edges from this node: {edges}")

if __name__ == "__main__":
    main()
