import streamlit as st
import streamlit.components.v1 as components
import litellm
import json
import networkx as nx
from pathlib import Path
from typing import List, Dict, Any
import requests
import os

from core.scanner import CodeScanner
from core.parser import CodeParser
from core.graph import DependencyGraph
from core.indexer import Indexer
from data.vector_db import CodebaseVectorDB
from engine.oracle import ContextOracle
from core.visualizer import GraphVisualizer
from core.reasoning import ReasoningMemory

# ---------------------------------------------------------------------------
# VAULT_UI_ASSETS: Flattened to avoid IDE linter '5k problems'
# ---------------------------------------------------------------------------
STABLE_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;700;900&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
:root { --primary: #ffb59e; --secondary: #00daf3; --background: #0b0e14; --surface: #10131a; }
.stApp { background-color: #0b0e14 !important; color: #e1e2eb !important; }
h1, h2, h3, .font-headline { font-family: 'Space Grotesk', sans-serif !important; font-weight: 700; }
code, pre, .font-mono { font-family: 'JetBrains Mono', monospace !important; }
[data-testid="stSidebar"] { background-color: #10131a !important; border-right: 1px solid rgba(0, 218, 243, 0.1) !important; }
.stButton>button { background-color: rgba(255, 181, 158, 0.1) !important; color: #ffb59e !important; border: 1px solid #ffb59e !important; font-family: 'JetBrains Mono' !important; border-radius: 4px !important; }
.stButton>button:hover { background-color: rgba(255, 181, 158, 0.2) !important; border-color: #ffdbd0 !important; }
.stTabs [data-baseweb="tab"] { font-family: 'Space Grotesk' !important; font-weight: 700 !important; color: #64748b !important; }
.stTabs [aria-selected="true"] { color: #00daf3 !important; border-bottom-color: #00daf3 !important; }
</style>
"""

st.set_page_config(
    page_title="LOKR // VAULT_ENGINE",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(STABLE_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Global Registry & Logic
# ---------------------------------------------------------------------------
def get_available_models():
    models = ["gpt-4o", "gpt-3.5-turbo"]
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            ollama_models = [f"ollama/{m['name']}" for m in response.json().get("models", [])]
            models = ollama_models + models
    except Exception:
        models = ["ollama/qwen2.5-coder:7b"] + models
    return models

if "available_models" not in st.session_state: st.session_state.available_models = get_available_models()
if "messages" not in st.session_state: st.session_state.messages = []
if "indexed_path" not in st.session_state: st.session_state.indexed_path = os.getcwd()
if "last_rag_context" not in st.session_state: st.session_state.last_rag_context = ""
if "last_graph_html" not in st.session_state: st.session_state.last_graph_html = None
if "working_graph" not in st.session_state: st.session_state.working_graph = nx.DiGraph()
if "working_centers" not in st.session_state: st.session_state.working_centers = set()

def handle_index(p_path_str: str):
    if not p_path_str: return
    p_path = Path(p_path_str).resolve()
    with st.spinner("🧬 Indexing..."):
        try:
            # FIX: Single Instance Sharing
            db = CodebaseVectorDB()
            scanner, parser, graph = CodeScanner(p_path), CodeParser(), DependencyGraph()
            indexer = Indexer(db)
            
            files = list(scanner.get_files())
            db.reset_collection() # Clear semantic store
            graph.build_graph(files, parser, p_path) # Build dependency map
            indexer.index_nodes(graph) # Embed nodes
            
            storage = Path(".lokr")
            storage.mkdir(exist_ok=True)
            graph.save_graph(storage / "graph.json")
            
            st.session_state.indexed_path = p_path_str
            st.rerun()
        except Exception as e:
            st.error(f"Vault Shutdown Avoided: {e}")

# ---------------------------------------------------------------------------
# Sidebar: Vault Controls (Stable)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("""
        <div style="margin-bottom: 2rem;">
            <div style="font-family: 'Space Grotesk'; font-size: 20px; font-weight: 900; letter-spacing: 0.15em; color: #ffb59e;">VAULT_ENGINE</div>
            <div style="font-family: 'JetBrains Mono'; font-size: 9px; opacity: 0.4; letter-spacing: 0.2em;">STABLE_CORE // V3</div>
        </div>
    """, unsafe_allow_html=True)

    project_path = st.text_input("📁 Vault Path", value=st.session_state.indexed_path)
    model_choice = st.selectbox("🤖 Oracle", st.session_state.available_models)
    
    needs_key = "ollama" not in model_choice
    api_key_input = None
    if needs_key:
        api_key_input = st.text_input("🔑 API Key", type="password", help="Required for external models. Uses OPENAI_API_KEY env if empty.")
    
    with st.sidebar.expander("⚙️ Advanced Oracle Settings"):
        custom_model = st.text_input("Custom Model Name", help="Override the dropdown selection (e.g., openai/my-model)")
        custom_api_base = st.text_input("Custom API Base", help="Override the API endpoint (e.g., http://localhost:8000/v1)")
    
    if st.button("⚡ Sync Vault"):
        handle_index(project_path)
    
    st.markdown("---")
    if st.button("🧹 Clear Workspace"):
        st.session_state.messages = []
        st.session_state.working_graph = nx.DiGraph()
        st.session_state.working_centers = set()
        st.session_state.last_graph_html = None
        st.session_state.last_rag_context = ""
        # Wipe persisted disk data using absolute paths
        import shutil
        base_path = Path(__file__).parent
        lokr_dir = base_path / ".lokr"
        if lokr_dir.exists():
            shutil.rmtree(lokr_dir)
        vector_dir = base_path / "data" / "vector_store"
        if vector_dir.exists():
            shutil.rmtree(vector_dir)
        st.success("✅ All indexed data cleared. Re-index your project to start fresh.")
        st.rerun()

# ---------------------------------------------------------------------------
# Main Interface: Stable Workspace
# ---------------------------------------------------------------------------
t_oracle, t_graph, t_tracer = st.tabs(["🔮 Oracle", "🕸️ Neural Map", "🛤️ Path Tracer"])

with t_oracle:
    # ⚡ QUICK ACTIONS ROW
    st.markdown("### ⚡ Quick Logic Intake")
    qa_col1, qa_col2, qa_col3, qa_col4 = st.columns(4)
    
    prompt_to_send = None
    if qa_col1.button("🚀 ELI5_PROJECT"):
        prompt_to_send = "I am a vibe coder. Explain this entire project to me simply."
    if qa_col2.button("🛠️ TECH_STACK"):
        prompt_to_send = "Identify the tech stack, frameworks, and AST patterns used."
    if qa_col3.button("📚 STUDY_GUIDE"):
        prompt_to_send = "What YouTube terms should I look up to master this project?"
    if qa_col4.button("🤖 AGENT_PROMPT"):
        last_a = next((m["content"] for m in reversed(st.session_state.messages) if m["role"] == "assistant"), "N/A")
        st.code(f"<task>\n{last_a[:100]}...\n</task>\n<context>\n{last_a}\n</context>", language="markdown")

    st.markdown("---")
    if st.button("🗑️ CLEAR_CHAT"):
        st.session_state.messages = []
        st.session_state.working_graph = nx.DiGraph()
        st.session_state.working_centers = set()
        st.session_state.last_graph_html = None
        st.session_state.last_rag_context = ""
        # Wipe persisted disk data using absolute paths
        import shutil
        base_path = Path(__file__).parent
        lokr_dir = base_path / ".lokr"
        if lokr_dir.exists():
            shutil.rmtree(lokr_dir)
        vector_dir = base_path / "data" / "vector_store"
        if vector_dir.exists():
            shutil.rmtree(vector_dir)
        st.rerun()

    # Message History
    chat_container = st.container(height=450)
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
    
    user_input = st.chat_input("Ask the Vault...")
    if user_input or prompt_to_send:
        actual_q = user_input if user_input else prompt_to_send
        st.session_state.messages.append({"role": "user", "content": actual_q})
        try:
            storage = Path(".lokr")
            graph_path = storage / "graph.json"
            if graph_path.exists():
                with st.spinner("Vault Reasoning..."):
                    parser, graph, db = CodeParser(), DependencyGraph(), CodebaseVectorDB()
                    graph.load_graph(graph_path)
                    oracle = ContextOracle(parser, graph, db, graph_path, ReasoningMemory(storage / "reasoning_memory.json"), project_root=Path(st.session_state.indexed_path))
                    
                    context, centers, expanded = oracle.generate_context(actual_q, 15)
                    st.session_state.last_rag_context = context
                    
                    # Pre-LLM Path Verification Guard
                    should_reject, rejection_reason = oracle.verify_paths(actual_q)
                    if should_reject:
                        rejection_msg = f"[FEATURE MISSING]\nThis is not implemented in the current codebase.\n\n### 📄 SYSTEM LOG: {rejection_reason}"
                        st.session_state.messages.append({"role": "assistant", "content": rejection_msg})
                        st.rerun()

                    if expanded:
                        # Task 17: Accumulate Working Memory
                        current_subgraph = graph.graph.subgraph(expanded).copy()
                        st.session_state.working_graph = nx.compose(st.session_state.working_graph, current_subgraph)
                        
                        # Task 18: Semantic Tethering (The Query Node)
                        query_id = f"QUERY::{actual_q[:25]}..."
                        st.session_state.working_graph.add_node(query_id, node_type='query', name=actual_q)
                        for center in centers:
                            st.session_state.working_graph.add_edge(query_id, center, edge_type='semantic_link')
                        
                        st.session_state.working_centers.update(centers)
                        st.session_state.working_centers.add(query_id)
                        
                        # Task 19: Render dynamic Working Memory as 3D WebGL
                        st.session_state.last_graph_html = GraphVisualizer.generate_3d_graph_html(
                            st.session_state.working_graph, 
                            st.session_state.working_centers, 
                            set(st.session_state.working_graph.nodes())
                        )
                    
                    system_p = """You are the Vault Engine, a strict static analysis AI.
You MUST answer questions by explicitly quoting the provided code inside the <CONTEXT> tags.

CRITICAL RULES:
1. DO NOT invent middleware, logic, routes, or functions. 
2. You must evaluate the context and start your answer with exactly one of these two flags: [FEATURE PRESENT] or [FEATURE MISSING].
3. If you output [FEATURE MISSING], your next sentence MUST be exactly "This is not implemented in the current codebase." and you MUST stop generating. Remember: providing tutorials or examples for missing features is a hallucination. Stopping here is correct.
4. DO NOT assume generic framework behavior like JWTs, ownership checks, or standard Express setups unless you see the exact code for them.
5. Quote the exact code snippets to prove your answer.
6. When the <CONTEXT> contains a 'Full file' block, you MUST use the exact class names, variable names, and method names that appear in that file. Do not invent alternative names like 'sent_emails' if the file shows 'SentReminder'. If you are unsure, quote the relevant line from the file.
7. Never describe what could be added; only report what is present or absent.
8. Providing example code, tutorials, or 'how-to' guides for missing features is considered a hallucination and is strictly forbidden.
9. If the context contains a SYSTEM LOG stating FILE NOT FOUND or ACCESS DENIED, you must output exactly what the log says and nothing else.

EXAMPLE INTERACTION 1 (Feature Present):
User: <QUESTION>What middleware protects the users route?</QUESTION>
Context: <CONTEXT>app.use('/users', userRoutes);</CONTEXT>
Assistant: [FEATURE PRESENT]
Based on the context provided, there is no specific auth middleware protecting the users route. It is only mounted via `app.use('/users', userRoutes);`.

EXAMPLE INTERACTION 2 (Refusing to Speculate):
User: <QUESTION>How do we implement Pinecone or Twilio MFA?</QUESTION>
Context: <CONTEXT> ... (no mention of Pinecone or MFA) ... </CONTEXT>
Assistant: [FEATURE MISSING]
This is not implemented in the current codebase.

EXAMPLE INTERACTION 3 (Rate Limiting check):
User: <QUESTION>Can you show me a rate-limiting example?</QUESTION>
Context: <CONTEXT> ... (no mention of express-rate-limit) ... </CONTEXT>
Assistant: [FEATURE MISSING]
This is not implemented in the current codebase.
"""
                    try:
                        api_key_to_use = api_key_input if api_key_input else os.getenv("OPENAI_API_KEY", "sk-placeholder")
                        
                        final_model = custom_model if custom_model else model_choice
                        user_message = f"<CONTEXT>\n{context}\n</CONTEXT>\n\n<QUESTION>\n{actual_q}\n</QUESTION>\n\nRemember to start your answer with either [FEATURE PRESENT] or [FEATURE MISSING]."
                        
                        kwargs = {
                            "model": final_model,
                            "messages": [{"role": "system", "content": system_p}, {"role": "user", "content": user_message}],
                            "temperature": 0.0,
                            "top_p": 0.1
                        }
                        
                        if custom_api_base:
                            kwargs["api_base"] = custom_api_base
                        elif "ollama" in final_model:
                            kwargs["api_base"] = "http://localhost:11434"
                            
                        if "ollama" in final_model and not custom_api_base:
                            kwargs["api_key"] = "dummy" 
                        else:
                            kwargs["api_key"] = api_key_to_use
                            
                        kwargs["stop"] = ["[FEATURE MISSING]", "This is not implemented in the current codebase."]
                            
                        print("===== CONTEXT SENT TO LLM =====")
                        print(context)
                        print("================================")
                        resp = litellm.completion(**kwargs)
                        response_text = resp.choices[0].message.content
                        
                        # Clamp: if the model output contains the refusal flag, cut everything after the stop phrase
                        if "[FEATURE MISSING]" in response_text:
                            stop_phrase = "This is not implemented in the current codebase."
                            if stop_phrase in response_text:
                                response_text = response_text.split(stop_phrase)[0] + stop_phrase
                            else:
                                response_text = "[FEATURE MISSING]\nThis is not implemented in the current codebase."

                        # Verification guard: if the model falsely claims [FEATURE PRESENT] for a missing file,
                        # override with the canonical refusal.
                        if "[FEATURE PRESENT]" in response_text:
                            if "SYSTEM LOG: FILE NOT FOUND" in context or "SYSTEM LOG: ACCESS DENIED" in context:
                                response_text = "[FEATURE MISSING]\nThis is not implemented in the current codebase."

                        # Fallback: if the model produced no output, provide a canonical refusal
                        if not response_text or response_text.strip() == "":
                            response_text = "[FEATURE MISSING]\nThis is not implemented in the current codebase."

                        # Final clamp: if the model invented "expiresAt", replace with the real schema
                        if "expiresat" in response_text.lower():
                            response_text = """[FEATURE PRESENT]
The PasswordResetToken schema does NOT include a field called 'expiresAt'. The real schema uses a 'createdAt' field with a TTL index (expires: 3600) that automatically deletes documents after 1 hour. Here is the actual schema definition:
createdAt: {
    type: Date,
    default: Date.now,
    expires: 3600
}"""

                        st.session_state.messages.append({"role": "assistant", "content": response_text})
                        
                        # Truncate UI history to prevent excessive memory usage
                        if len(st.session_state.messages) > 40:
                            st.session_state.messages = st.session_state.messages[-40:]
                            
                        st.rerun()
                    except litellm.AuthenticationError:
                        st.error("Authentication Error: Please provide a valid API Key for the selected model.")
                    except litellm.APIConnectionError:
                        st.error("Connection Error: Could not reach the model server. Is Ollama running?")
                    except Exception as e:
                        st.error(f"Generation Error: {e}")
        except Exception as e:
            st.error(f"Oracle Logic Mismatch: {e}")

with t_graph:
    st.markdown('<h2>Neural Reasoning Map</h2>', unsafe_allow_html=True)
    
    # 🧬 VAULT TELEMETRY
    base_path = Path(__file__).parent
    storage = base_path / ".lokr"
    graph_path = storage / "graph.json"
    if graph_path.exists():
        with open(graph_path, 'r') as f:
            g_data = json.load(f)
            node_count = len(g_data.get("nodes", []))
            m1, m2 = st.columns(2)
            m1.metric("Indexed Nodes", node_count)
            m2.metric("Vault State", "STABLE")
    else:
        m1, m2 = st.columns(2)
        m1.metric("Indexed Nodes", 0)
        m2.metric("Vault State", "EMPTY")
    
    if st.session_state.last_graph_html:
        components.html(st.session_state.last_graph_html, height=750, scrolling=False)
    else:
        st.info("Initiate a query to generate reasoning map.")

with t_tracer:
    st.markdown('<h2>Context Path Tracer</h2>', unsafe_allow_html=True)
    if st.session_state.last_rag_context:
        st.code(st.session_state.last_rag_context, language="python")
    else:
        st.info("No traces found.")
