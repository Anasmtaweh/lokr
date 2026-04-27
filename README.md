<div align="center">

# Lokr

**The privacy-first, Graph-RAG code intelligence engine for local LLMs.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Powered by Ollama](https://img.shields.io/badge/Powered%20by-Ollama-black)](https://ollama.com)

</div>

---

## What is Lokr?

Lokr is a **100% local**, GPU-accelerated code intelligence engine. It indexes your entire codebase using AST parsing and a semantic vector store, then gives your local Ollama LLM (DeepSeek, Qwen, Mistral, etc.) the precise context it needs to answer questions, diagnose bugs, and generate structured prompts — without sending a single byte to the cloud.

**No API keys. No subscriptions. No cloud. Just your GPU.**

---

## Features

- **Polyglot AST Parsing** — Python, JavaScript, TypeScript, PHP, HTML, CSS via Tree-sitter
- **Dependency Graph** — NetworkX-powered import graph to trace code relationships
- **Hybrid RAG Search** — Semantic (ChromaDB) + keyword scan, combined into rich context
- **Persistent Memory Bank** — Save architectural decisions and inject them as AI GPS
- **Auto-Build Master Blueprint** — 1-click AST-enriched architectural overview injected into memory
- **Auto-Coder Prompt Generator** — Converts Oracle diagnoses into structured XML prompts for Cursor/Copilot
- **Streamlit Chat UI** — Full chat interface with reasoning display and file explorer
- **MCP Server** — Exposes the Oracle as an MCP tool for AI agent integration
- **Git Watchman** — Incremental re-indexing using `git status` — only re-processes changed files
- **Local + Cloud Modes** — Switch between Ollama (local GPU) and cloud APIs (GPT-4o, Claude, Gemini)

---

## Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/) installed and running locally
- An Ollama model pulled (e.g., `ollama pull qwen2.5-coder:7b`)
- An NVIDIA GPU (recommended: 6GB+ VRAM) or CPU fallback

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/Anasmtaweh/lokr.git
cd lokr

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch the Streamlit UI
streamlit run app.py
```

### First Run

1. Open your browser at `http://localhost:8501`
2. Paste the **absolute path** to your project in the sidebar (e.g., `/home/user/my-project`)
3. Select your local Ollama model
4. Click **Index Project**
5. Ask anything in the chat!

---

## Architecture

```
lokr/
├── app.py                  # Streamlit Chat UI & RAG pipeline orchestrator
├── main.py                 # CLI entry point (scan, parse, graph, index, ask, mcp)
├── config.yaml             # Scanner configuration (ignored dirs/extensions)
│
├── core/
│   ├── scanner.py          # File discovery with .gitignore-aware filtering
│   ├── parser.py           # Polyglot AST extractor (Python, JS, TS, PHP, HTML, CSS)
│   └── graph.py            # NetworkX dependency graph builder
│
├── data/
│   ├── vector_db.py        # ChromaDB semantic vector store (index, search, delete)
│   └── git_tools.py        # Git Watchman — tracks changed files via git status
│
└── engine/
    ├── oracle.py           # ContextOracle — fuses RAG + graph into Markdown context
    └── mcp_server.py       # MCP stdio server for AI agent tool integration
```

---

## Supported Models

Lokr works with any Ollama model and major cloud providers via LiteLLM.

| Model | Provider | Best For |
|---|---|---|
| `qwen2.5-coder:7b` | Ollama (local) | Code understanding & bug diagnosis |
| `deepseek-r1:8b` | Ollama (local) | Reasoning-heavy architectural questions |
| `mistral-nemo:12b` | Ollama (local) | General purpose (requires more VRAM) |
| `gpt-4o` | OpenAI | Highest accuracy cloud option |
| `claude-3-5-sonnet-20241022` | Anthropic | Long-context code analysis |
| `gemini/gemini-1.5-pro` | Google | Fast cloud reasoning |

---

## CLI Usage

```bash
# Scan a project
python main.py --scan /path/to/project

# Parse a single file (outputs AST JSON)
python main.py --parse /path/to/file.py

# Index entire project into Vector DB
python main.py --index

# Semantic search
python main.py --search "how does authentication work"

# Ask the Oracle (outputs Markdown context)
python main.py --ask "what does the login function do"

# Start MCP server (for AI agent integration)
python main.py --mcp
```

---

## Privacy & Security

- **All processing is local by default.** No data is sent to any external service when using Ollama.
- **ChromaDB runs locally** as an embedded SQLite + Parquet store.
- **Ollama runs locally.** Your code never leaves your machine.
- The `.gitignore` is configured to **never commit** the vector store, model weights, or virtual environments.
- Cloud mode is opt-in — your API key is never stored or logged.

---

## License

MIT — see [LICENSE](./LICENSE) for details.

---

## Author

Built by [Anas Mtaweh](https://github.com/Anasmtaweh) 

- GitHub: [Anasmtaweh](https://github.com/Anasmtaweh)
- LinkedIn: [linkedin.com/in/anas-mtaweh-a02806218](https://www.linkedin.com/in/anas-mtaweh-a02806218)
