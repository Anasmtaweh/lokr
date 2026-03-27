import argparse
import sys
import json
from pathlib import Path

from core.scanner import CodeScanner
from core.parser import CodeParser
from core.graph import DependencyGraph
from data.vector_db import CodebaseVectorDB
from data.git_tools import GitWatchman
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
            dep_graph.build_graph(file_paths=project_files, parser=code_parser)
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
        print("[*] Commencing Phase 4: Codebase Aggregation & Indexing...")
        try:
            scanner = CodeScanner(target_dir=project_root, config_path=args.config)
            parser_engine = CodeParser()
            vector_db = CodebaseVectorDB()
            project_files = list(scanner.get_files())
            successful_indexes = 0
            for fp in project_files:
                try:
                    parsed_json = parser_engine.parse_file(fp)
                    vector_db.index_file(parsed_json)
                    successful_indexes += 1
                except Exception as chunk_err:
                    print(f" [WARN] Failed to embed {fp}: {chunk_err}", file=sys.stderr)
            print(f"[SUCCESS] Indexed {successful_indexes} files into persistent memory.")
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
                print(f"\n[{idx}] File: {rel_path} | Distance Score: {res['distance']:.4f}")
            print("\n---------------------------------------------------------")
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

    # Phase 5: Incremental Update
    elif args.update:
        try:
            watchman = GitWatchman()
            modified_files, deleted_files = watchman.get_changed_files(project_root)
            scanner = CodeScanner(target_dir=project_root, config_path=args.config)
            valid_project_files = set(scanner.get_files())
            filtered_modified = [fp for fp in modified_files if fp in valid_project_files]
            vector_db = CodebaseVectorDB()
            parser_engine = CodeParser()
            deleted_count = 0
            for fp in deleted_files:
                vector_db.delete_file(fp)
                deleted_count += 1
            updated_count = 0
            for fp in filtered_modified:
                try:
                    parsed_json = parser_engine.parse_file(fp)
                    vector_db.index_file(parsed_json)
                    updated_count += 1
                except Exception as e:
                    print(f" [WARN] Could not re-index {fp}: {e}", file=sys.stderr)
            print(f"[WATCHMAN] Fast-sync complete: {updated_count} updated, {deleted_count} deleted.")
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
            dep_graph.build_graph(file_paths=project_files, parser=code_parser)
            oracle = ContextOracle(parser=code_parser, graph=dep_graph, db=vector_db)
            context_markdown = oracle.generate_context(query=args.ask)
            print(context_markdown)
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
