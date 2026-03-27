from pathlib import Path

from mcp.server.fastmcp import FastMCP

from core.scanner import CodeScanner
from core.parser import CodeParser
from core.graph import DependencyGraph
from data.vector_db import CodebaseVectorDB
from engine.oracle import ContextOracle

# Project root is resolved relative to this file's location (engine/mcp_server.py -> project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Initialize the FastMCP server instance
mcp = FastMCP("DevOps Context Oracle")


@mcp.tool()
def ask_oracle(query: str) -> str:
    """
    Queries the local codebase using a Graph-RAG engine.
    Use this when the user asks how the code works, where logic is located,
    or asks for refactoring context.

    Args:
        query (str): A natural language question about the codebase.

    Returns:
        str: A rich Markdown context block fusing semantic search, AST structure,
             and dependency graph data relevant to the query.
    """
    # 1. Scan for all valid project files
    scanner = CodeScanner(
        target_dir=_PROJECT_ROOT,
        config_path=str(_PROJECT_ROOT / "config.yaml")
    )
    project_files = list(scanner.get_files())

    # 2. Instantiate engine components
    code_parser = CodeParser()
    vector_db = CodebaseVectorDB(db_dir=str(_PROJECT_ROOT / "data" / "vector_store"))
    dep_graph = DependencyGraph()

    # 3. Build the dependency graph topology
    dep_graph.build_graph(file_paths=project_files, parser=code_parser)

    # 4. Instantiate Oracle and generate context markdown
    oracle = ContextOracle(parser=code_parser, graph=dep_graph, db=vector_db)
    return oracle.generate_context(query=query)


def run_mcp_server() -> None:
    """
    Starts the FastMCP server in stdio transport mode.
    This is the entry point for MCP clients (e.g., Claude Desktop, VS Code agents).

    CRITICAL: No stdout output must occur before or during mcp.run().
    MCP communicates exclusively via JSON-RPC over stdio.
    """
    mcp.run()
