<div align="center">

# Lokr

**The privacy-first, Graph-RAG code intelligence engine for local LLMs.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Powered by Ollama](https://img.shields.io/badge/Powered%20by-Ollama-black)](https://ollama.com)

</div>

---

## What is Lokr?

Lokr is a **local-first**, GPU-accelerated code intelligence engine. It indexes your entire codebase using AST parsing and a semantic vector store, then gives your LLM (DeepSeek, Qwen, Mistral, etc.) the precise context it needs to answer questions, diagnose bugs, and generate structured prompts.

**Built for absolute privacy. Run it entirely on your local GPU, or connect to remote open-weight models on your own rented infrastructure.**

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
- **Local + Remote Modes** — Switch between local Ollama and remote OpenAI-compatible endpoints (e.g., vLLM on rented GPUs)

---

## Reliability & Grounding

Lokr includes multiple **programmatic clamps** to prevent the LLM from inventing non‑existent features:

- **Forced Categorical Flags** – Every answer starts with `[FEATURE PRESENT]` or `[FEATURE MISSING]`, forcing the model to decide what actually exists.
- **Automatic Stop Sequences** – The API stops generating immediately after “This is not implemented in the current codebase.” — no tutorials, no invented middleware, no hallucinated code.
- **File Facts Injection** – When a file is injected into context, a bullet list of verified class/function names is prepended so the model can't invent alternative names (e.g., `sent_emails` instead of `SentReminder`).
- **System Log Awareness** – Missing or blocked files generate explicit `SYSTEM LOG` entries (`FILE NOT FOUND`, `ACCESS DENIED`) so the LLM never guesses about file contents.

---

## Benchmarks & Reliability Testing

Lokr is tested continuously against real, undocumented codebases to ensure its AST Context Retriever and static analysis clamps hold up against diverse architectures. We don't over-sell these projects—they are real-world codebases with realistic flaws.

**1. Standard MVC Architecture (`pet-ai-project`)**
- **Profile:** A standard 10,000-line Express/React web application.
- **Difficulty:** 6.5/10 (High file density, standard web patterns).
- **Score:** **99% Accuracy (95/96 queries passed)**
- **Takeaway:** Lokr easily navigated standard MVC boilerplate. It correctly identified missing Docker setups and hallucination traps, but failed exactly once when asked to predict the runtime `.env` port without seeing the `.env` file.

**2. Abstract Mathematical Architecture (`ML_Gen2`)**
- **Profile:** A 6,600-line Reinforcement Learning codebase (AlphaZero MCTS & D3QN Tensor math). Zero standard web scaffolding.
- **Difficulty:** 8.5/10 (Highly abstract, deep multi-hop neural network tracking).
- **Score:** **83.3% Accuracy (10/12 brutal multi-hop queries passed)**
- **Takeaway:** Lokr scored 100% on the static code questions, successfully tracking tensor shapes and missing LSTM layers across multiple files. It lost 2 points exclusively on *Runtime Ambiguity Traps* (it successfully traced the absolute file path generation, but failed to realize that absolute paths cannot be determined statically since they depend on the host machine).

### Transparent Testing: See for Yourself

We don't expect you to take our word for it. The exact autonomous evaluation harness used to generate these scores is included in the repository.

**Example "Hard Mode" Questions we throw at Lokr:**
- *(Factual / Multi-hop)*: "In `network.py`, what is the exact number of output channels for the `conv1` layer in the `AlphaZeroNet` class?"
- *(Adversarial / Hallucination Trap)*: "Does the `AlphaZeroNet` implementation use an LSTM or GRU layer to track sequential board states over time?"
- *(Runtime Trap)*: "What is the exact port number the Flask server binds to when executed via an external Docker Compose network mapping at runtime?"

**Run the QA Harness on your own project:**
```bash
# The Kimi k2p6 Judge will autonomously read your project, generate 12 tests, run Lokr, verify the citations, and grade the output.
python tests/qa_evaluator.py --target /path/to/your/project --api-key YOUR_FIREWORKS_API_KEY
```

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
│   ├── indexer.py          # Node embedding pipeline for the vector store
│   ├── retriever.py        # Semantic search + graph-guided context expansion
│   ├── visualizer.py       # 2D & 3D subgraph rendering (Matplotlib + 3D-force-graph)
│   ├── reasoning.py        # Persistent global reasoning memory
│   └── graph.py            # NetworkX dependency graph builder
│
├── data/
│   ├── vector_db.py        # ChromaDB semantic vector store (index, search, delete)
│   └── git_tools.py        # Git Watchman — tracks changed files via git status
│
└── engine/
    ├── oracle.py           # ContextOracle — fuses RAG + graph into Markdown context
    └── mcp_server.py       # MCP stdio server for AI agent integration
```

---

## Supported Models

Lokr works with any local Ollama model, as well as remote OpenAI-compatible endpoints (perfect for running open-weight models on rented cloud GPUs via vLLM or LiteLLM).

| Model | Provider | Best For |
|---|---|---|
| `qwen2.5-coder:7b` | Ollama / Alibaba | Code understanding & bug diagnosis |
| `deepseek-r1:8b` | Ollama / DeepSeek | Reasoning-heavy architectural questions |
| `mistral-nemo:12b` | Ollama / Mistral | General purpose (requires more VRAM) |
| `llama-3.1-8b` | Ollama / Meta | Strong all-around performance |
| `qwen2.5-coder-32b` | Remote API | Maximum context and reasoning capability |

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

# Incremental git-sync (re-index only changed files)
python main.py --update

# Ask the Oracle (outputs Markdown context)
python main.py --ask "what does the login function do"

# Start MCP server (for AI agent integration)
python main.py --mcp
```

---

## Privacy & Security

- **ChromaDB runs locally** as an embedded SQLite + Parquet store.
- **The `.gitignore` is configured to never commit** the vector store, model weights, or virtual environments.
- **Two Privacy Postures:**
  - **Local Ollama:** 100% private. Your code never leaves your machine. No data is sent to any external service.
  - **Remote APIs:** Opt-in routing for rented GPUs (e.g., running open-weight models on a cloud instance you control). Your endpoint URL and API keys are never stored or logged.

---

## License

MIT — see [LICENSE](./LICENSE) for details.

---

## Author

Built by [Anas Mtaweh](https://github.com/Anasmtaweh) 

- GitHub: [Anasmtaweh](https://github.com/Anasmtaweh)
- LinkedIn: [linkedin.com/in/anas-mtaweh-a02806218](https://www.linkedin.com/in/anas-mtaweh-a02806218)
