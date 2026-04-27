import argparse
import sys
import json
from pathlib import Path

from core.scanner import CodeScanner
from core.parser import CodeParser
from core.graph import DependencyGraph
from core.indexer import Indexer
from data.vector_db import CodebaseVectorDB
from engine.oracle import ContextOracle
from engine.mcp_server import run_mcp_server

def main() -> None:
    """
    Entry point for the Lokr CLI.
    Provides command-line interactions for all engine phases.
    """
    parser = argparse.ArgumentParser(
        description="Lokr — Privacy-first Graph-RAG Code Intelligence Engine",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument("--scan",   type=str,           metavar="DIRECTORY", help="Phase 1: Scan a directory and list valid source files")
    parser.add_argument("--parse",  type=str,           metavar="FILEPATH",  help="Phase 2: Parse a file and output its AST as JSON")
    parser.add_argument("--graph",  type=str,           metavar="FILEPATH",  help="Phase 3: Show which files import the target file")
    parser.add_argument("--index",  action="store_true",                     help="Phase 4: Embed all valid files into the local Vector DB")
    parser.add_argument("--search", type=str,           metavar="QUERY",     help="Phase 4: Semantic search across the codebase Vector DB")
    parser.add_argument("--update", action="store_true",                     help="Phase 5: Incremental fast-sync of git-changed files")
    parser.add_argument("--ask",    type=str,           metavar="QUERY",     help="Phase 6: Ask the Oracle to generate rich Markdown context")
    parser.add_argument("--mcp",    action="store_true",                     help="Phase 7: Start the stdio MCP server for AI agent integration")
    parser.add_argument("--config", type=str, default="config.yaml",         help="Path to config yaml (default: config.yaml)")

    args = parser.parse_args()
    project_root = Path(".").resolve()

    # Phase 7: MCP Server — MUST be checked first, no stdout allowed after this point
    if args.mcp:
        run_mcp_server()
        sys.exit(0)

    # Phase 1: Scan
    elif args.scan:
        scan_dir = Path(args.scan).resolve()
        print(f"Starting Phase 1: Scanning directory -> {scan_dir}")
        try:
            scanner = CodeScanner(target_dir=scan_dir, config_path=args.config)
            file_count: int = 0
            for file_path in scanner.get_files():
                print(file_path)
                file_count += 1
            print(f"\n[SUCCESS] Scan complete. Discovered {file_count} valid source files.")
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

    # Phase 2: Parse
    elif args.parse:
        parse_file = Path(args.parse).resolve()
        try:
            code_parser = CodeParser()
            result = code_parser.parse_file(parse_file)
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

    # Phase 3: Graph
    elif args.graph:
        target_file = Path(args.graph).resolve()
        try:
            scanner = CodeScanner(target_dir=project_root, config_path=args.config)
            project_files = list(scanner.get_files())
            code_parser = CodeParser()
            dep_graph = DependencyGraph()
            
            # Graph Persistence Logic
            storage_dir = Path(".lokr")
            graph_path = storage_dir / "graph.json"
            
            if graph_path.exists():
                dep_graph.load_graph(graph_path)
                # Sync with git to handle modifications/additions/deletions incrementally
                if dep_graph.sync_with_git(project_root, code_parser, project_files):
                    dep_graph.save_graph(graph_path)
            else:
                dep_graph.build_graph(file_paths=project_files, parser=code_parser, project_root=project_root)
                storage_dir.mkdir(exist_ok=True)
                dep_graph.save_graph(graph_path)
            dependents = dep_graph.get_dependents(target_file)
            print(f"\n[{target_file.name}] is imported by:")
            if not dependents:
                print("  - [No dependents found]")
            else:
                for dep in dependents:
                    try:
                        print(f"  - {Path(dep).relative_to(project_root)}")
                    except ValueError:
                        print(f"  - {dep}")
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

    # Phase 4: Index
    elif args.index:
        print("[*] Commencing Phase 4: Function-Level Node Indexing...")
        try:
            scanner = CodeScanner(target_dir=project_root, config_path=args.config)
            parser_engine = CodeParser()
            vector_db = CodebaseVectorDB()
            dep_graph = DependencyGraph()
            project_files = list(scanner.get_files())
            
            # Step 1: Build the complete Graph to discover all function nodes
            print("[1/2] Building hierarchical dependency graph...")
            dep_graph.build_graph(file_paths=project_files, parser=parser_engine, project_root=project_root)
            
            # Step 2: Extract and index individual functions
            print("[2/2] Embedding function nodes into vector database...")
            indexer = Indexer(vector_db)
            vector_db.reset_collection()
            indexer.index_nodes(dep_graph)
            
            # Save the graph state
            storage_dir = Path(".lokr")
            graph_path = storage_dir / "graph.json"
            storage_dir.mkdir(exist_ok=True)
            dep_graph.save_graph(graph_path)
            
            print(f"[SUCCESS] Codebase indexed at function-level granularity.")
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

    # Phase 4: Search
    elif args.search:
        try:
            vector_db = CodebaseVectorDB()
            results = vector_db.search(args.search, n_results=3)
            print(f"\n--- Semantic Search Results for: \"{args.search}\" ---")
            for idx, res in enumerate(results, 1):
                try:
                    rel_path = Path(res['file_path']).relative_to(project_root)
                except ValueError:
                    rel_path = res['file_path']
                node_name = res.get('node_id', '').split('::')[-1]
                print(f"\n[{idx}] File: {rel_path} | Function: {node_name} | Distance Score: {res['distance']:.4f}")
            print("\n---------------------------------------------------------")
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

    # Phase 5: Incremental Update
    elif args.update:
        print("[*] Commencing Phase 5: Incremental Git-Sync...")
        try:
            storage_dir = Path(".lokr")
            graph_path = storage_dir / "graph.json"
            
            if not graph_path.exists():
                print("[ERROR] No existing graph cache found. Please run --index first.")
                sys.exit(1)
                
            scanner = CodeScanner(target_dir=project_root, config_path=args.config)
            project_files = list(scanner.get_files())
            code_parser = CodeParser()
            vector_db = CodebaseVectorDB()
            dep_graph = DependencyGraph()
            indexer = Indexer(vector_db)
            
            dep_graph.load_graph(graph_path)
            
            # Synchronize with Git and collect function delta
            delta = dep_graph.sync_with_git(project_root, code_parser, project_files)
            
            # Update Vector Database incrementally
            if delta["deleted_nodes"]:
                print(f" [SYNC] Deleting {len(delta['deleted_nodes'])} function vectors...")
                indexer.delete_nodes(delta["deleted_nodes"])
            
            if delta["added_nodes"]:
                print(f" [SYNC] Indexing {len(delta['added_nodes'])} new function vectors...")
                indexer.index_node_list(delta["added_nodes"], dep_graph)
            
            # Save the updated graph state
            dep_graph.save_graph(graph_path)
            print(f"[SUCCESS] Fast-sync complete: {len(delta['added_nodes'])} updated, {len(delta['deleted_nodes'])} deleted.")
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

    # Phase 6: Ask the Oracle
    elif args.ask:
        try:
            scanner = CodeScanner(target_dir=project_root, config_path=args.config)
            project_files = list(scanner.get_files())
            code_parser = CodeParser()
            vector_db = CodebaseVectorDB()
            dep_graph = DependencyGraph()
            
            # Graph Persistence Logic
            storage_dir = Path(".lokr")
            graph_path = storage_dir / "graph.json"
            
            if graph_path.exists():
                dep_graph.load_graph(graph_path)
                # Sync with git to handle modifications/additions/deletions incrementally
                if dep_graph.sync_with_git(project_root, code_parser, project_files):
                    dep_graph.save_graph(graph_path)
            else:
                dep_graph.build_graph(file_paths=project_files, parser=code_parser, project_root=project_root)
                storage_dir.mkdir(exist_ok=True)
                dep_graph.save_graph(graph_path)
            oracle = ContextOracle(parser=code_parser, graph=dep_graph, db=vector_db, graph_path=graph_path, project_root=project_root)
            context_markdown, _, _ = oracle.generate_context(query=args.ask)
            print(context_markdown)
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
# Test comment
