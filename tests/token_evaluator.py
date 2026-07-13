import sys
import json
import argparse
from pathlib import Path

# Ensure Lokr imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner import CodeScanner
from core.parser import CodeParser
from core.graph import DependencyGraph
from core.indexer import Indexer
from data.vector_db import CodebaseVectorDB
from engine.oracle import ContextOracle

def count_tokens(text: str) -> int:
    """Rough estimation of tokens: 1 token ~= 4 characters."""
    return len(text) // 4

def run_token_benchmark(target_dir: Path, questions_file: Path):
    storage_dir = target_dir / ".lokr"
    storage_dir.mkdir(exist_ok=True)
    graph_path = storage_dir / "graph.json"

    scanner = CodeScanner(target_dir=target_dir)
    project_files = list(scanner.get_files())
    code_parser = CodeParser()
    vector_db = CodebaseVectorDB()
    dep_graph = DependencyGraph()

    # Fast programmatic graph build/load
    if graph_path.exists():
        dep_graph.load_graph(graph_path)
        if dep_graph.sync_with_git(target_dir, code_parser, project_files):
            dep_graph.save_graph(graph_path)
    else:
        dep_graph.build_graph(file_paths=project_files, parser=code_parser, project_root=target_dir)
        indexer = Indexer(vector_db)
        vector_db.reset_collection()
        indexer.index_nodes(dep_graph)
        dep_graph.save_graph(graph_path)

    oracle = ContextOracle(
        parser=code_parser, 
        graph=dep_graph, 
        db=vector_db, 
        graph_path=graph_path, 
        project_root=target_dir, 
        read_only=True
    )

    with open(questions_file, "r") as f:
        test_cases = json.load(f)

    total_lokr_tokens = 0
    total_standard_tokens = 0

    print(f"[*] Running Token Efficiency Benchmark on {target_dir.name}")
    print(f"[*] {len(test_cases)} questions loaded from {questions_file.name}\n")

    for i, test in enumerate(test_cases, 1):
        query = test['question']
        
        # 1. Get Lokr's AST Context
        context_markdown, _, expanded_node_ids = oracle.generate_context(query=query)
        lokr_tokens = count_tokens(context_markdown)
        total_lokr_tokens += lokr_tokens

        # 2. Extract which files Lokr touched from the nodes
        # Node format is usually "path/to/file.py::func_name" or "path/to/file.py:class:func"
        touched_files = set()
        for node_id in expanded_node_ids:
            if ":" in node_id:
                file_rel_path = node_id.split(":")[0]
                touched_files.add(file_rel_path)

        # 3. Simulate Standard Full-File RAG
        standard_text = ""
        for rel_path in touched_files:
            full_path = target_dir / rel_path
            if full_path.exists() and full_path.is_file():
                try:
                    standard_text += full_path.read_text(encoding="utf-8")
                except Exception:
                    pass
        
        # Standard RAG also includes the prompt overhead just like Lokr
        standard_tokens = count_tokens(standard_text)
        # Add a rough baseline for instructions/query
        standard_tokens += 150 
        total_standard_tokens += standard_tokens

        print(f"--- Q{i}: {query[:60]}... ---")
        print(f"  Lokr AST Tokens:      {lokr_tokens:,}")
        print(f"  Standard RAG Tokens:  {standard_tokens:,}")
        
        if standard_tokens > 0:
            reduction = ((standard_tokens - lokr_tokens) / standard_tokens) * 100
            print(f"  Token Reduction:      {reduction:.1f}%\n")
        else:
            print("  Token Reduction:      N/A\n")

    print("==========================================")
    print("=== FINAL TOKEN EFFICIENCY RESULTS ===")
    print(f"Total Lokr (AST) Tokens:     {total_lokr_tokens:,}")
    print(f"Total Standard (Full) Tokens: {total_standard_tokens:,}")
    
    if total_standard_tokens > 0:
        overall_reduction = ((total_standard_tokens - total_lokr_tokens) / total_standard_tokens) * 100
        print(f"\nOverall Context Reduction: {overall_reduction:.1f}%")
        print(f"Lokr is {total_standard_tokens / total_lokr_tokens:.1f}x more token-efficient than standard IDE RAG on this benchmark.")
    else:
        print("Could not compute reduction (Standard Tokens = 0).")
    print("==========================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Token Efficiency Evaluator")
    parser.add_argument("--target", type=str, required=True, help="Target project path to test")
    parser.add_argument("--questions-file", type=str, required=True, help="JSON file containing the questions")
    args = parser.parse_args()

    target_dir = Path(args.target).resolve()
    if not target_dir.exists():
        print(f"Error: Target directory {target_dir} not found.")
        sys.exit(1)

    q_file = Path(args.questions_file).resolve()
    if not q_file.exists():
        print(f"Error: Questions file {q_file} not found.")
        sys.exit(1)

    run_token_benchmark(target_dir, q_file)
