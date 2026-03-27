import streamlit as st
import litellm
from pathlib import Path
from typing import List, Dict, Any

from core.scanner import CodeScanner
from core.parser import CodeParser
from core.graph import DependencyGraph
from data.vector_db import CodebaseVectorDB
from engine.oracle import ContextOracle

# ---------------------------------------------------------------------------
# Page Configuration & Aesthetics
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Lokr — Code Intelligence",
    page_icon="🔮",
    layout="wide",
)

st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #ff4b4b;
        color: white;
    }
    .stTextInput>div>div>input {
        color: #fafafa;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session State for Persistence
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "indexed_path" not in st.session_state:
    st.session_state.indexed_path = None

if "project_files" not in st.session_state:
    st.session_state.project_files = []

if "retained_memory" not in st.session_state:
    st.session_state.retained_memory = ""

if "active_files" not in st.session_state:
    st.session_state.active_files = []

# ---------------------------------------------------------------------------
# Sidebar: Configuration
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Lokr Settings")
    st.markdown("---")
    
    project_path_input = st.text_input(
        "📁 Project Path",
        placeholder="/path/to/your/project",
        help="Absolute path to the local repository folder."
    )
    
    execution_mode = st.radio(
        "⚡ Execution Mode",
        options=["🖥️ Local (Ollama)", "☁️ Cloud API"],
        horizontal=True,
        help="Local: runs on your GPU via Ollama. Cloud: routes through a provider API key."
    )

    is_local = execution_mode == "🖥️ Local (Ollama)"

    if is_local:
        selected_model = st.selectbox(
            "🤖 Local AI Model (Ollama)",
            options=[
                "ollama/qwen2.5-coder:7b",
                "ollama/deepseek-r1:8b",
                "ollama/dolphin-llama3:8b",
                "ollama/whiterabbitneo:8b",
                "ollama/mistral-nemo:12b"
            ],
            help="Select your preferred local model from Ollama."
        )
        user_api_key = ""
    else:
        selected_model = st.selectbox(
            "☁️ Cloud Model",
            options=[
                "gpt-4o",
                "gpt-4o-mini",
                "claude-3-5-sonnet-20241022",
                "claude-3-haiku-20240307",
                "gemini/gemini-1.5-pro",
                "gemini/gemini-1.5-flash",
            ],
            help="Select a cloud model. Ensure you have a valid API key for the provider."
        )
        user_api_key = st.text_input(
            "🔑 API Key",
            type="password",
            placeholder="sk-... or your provider key",
            help="Your API key for the selected cloud provider. Never stored or logged."
        )
    
    st.markdown("---")
    index_button = st.button("⚡ Index Project")

    # -----------------------------------------------------------------------
    # Indexing Logic
    # -----------------------------------------------------------------------
    if index_button:
        if not project_path_input:
            st.error("Please provide a valid Project Path.")
        else:
            p_path = Path(project_path_input).resolve()
            if not p_path.is_dir():
                st.error(f"Directory not found: {p_path}")
            else:
                with st.spinner("🧬 Indexing codebase DNA..."):
                    try:
                        # 1. Initialize Backend
                        scanner = CodeScanner(target_dir=p_path)
                        code_parser = CodeParser()
                        
                        # Use folder name for collection or stick to default persistent store
                        v_db = CodebaseVectorDB(db_dir=str(p_path / "data" / "vector_store") if (p_path / "data").exists() else "data/vector_store")
                        
                        # 2. Scan and Index
                        files = list(scanner.get_files())
                        successful_count = 0
                        
                        for f in files:
                            try:
                                parsed = code_parser.parse_file(f)
                                v_db.index_file(parsed)
                                successful_count += 1
                            except Exception:
                                continue
                        
                        # Store in session state
                        st.session_state.indexed_path = str(p_path)
                        st.session_state.project_files = files
                        
                        st.success(f"Successfully indexed {successful_count} files!")
                    except Exception as e:
                        st.error(f"Indexing Error: {e}")

    if st.session_state.indexed_path:
        p_path = Path(st.session_state.indexed_path)
        # Ensure they are Path objects for easy property access
        all_rel_paths = [f.relative_to(p_path) for f in st.session_state.project_files]
        
        with st.expander("📁 Project File Explorer", expanded=True):
            st.caption("Uncheck a file to completely hide it from the AI's memory and search.")
            st.info("⚡ **Instant Update:** Unchecking files applies instantly to your next chat message. You do **not** need to re-index!")
            
            # 1. Build tabular data for the data_editor
            file_records = []
            for rp in all_rel_paths:
                folder = str(rp.parent) if str(rp.parent) != "." else "/"
                file_records.append({
                    "Active": True,
                    "Folder": folder,
                    "File": rp.name
                })
                
            # 2. Render the interactive grid
            edited_files = st.data_editor(
                file_records,
                column_config={
                    "Active": st.column_config.CheckboxColumn(
                        "Include", 
                        help="Check to allow the AI to read this file. Uncheck to hide it.", 
                        width="small"
                    ),
                    "Folder": st.column_config.TextColumn("Directory", disabled=True),
                    "File": st.column_config.TextColumn("File Name", disabled=True)
                },
                hide_index=True,
                width="stretch",
                height=350
            )
            
            # 3. Extract the paths that are still checked True
            active_rel_paths = [
                all_rel_paths[i] 
                for i, row in enumerate(edited_files) 
                if row["Active"]
            ]
            
        st.session_state.active_files = [p_path / rp for rp in active_rel_paths]
    else:
        st.warning("⚠️ No project indexed.")

    st.markdown("---")
    st.subheader("🧠 Active Memory Bank")
    st.caption("Edit this text to control exactly what the AI remembers. Delete what isn't important to save GPU VRAM.")

    # --- Auto-Build Master Blueprint ---
    if st.button("🗺️ Auto-Build Master Blueprint"):
        if not st.session_state.indexed_path:
            st.error("Please index a project first.")
        else:
            with st.spinner("🧠 Scanning architecture & building Master Blueprint..."):
                try:
                    p_path = Path(st.session_state.indexed_path)
                    code_parser = CodeParser()
                    enriched_map_lines = []

                    for fp in st.session_state.active_files:
                        try:
                            rel = Path(fp).relative_to(p_path)
                        except ValueError:
                            rel = Path(fp).name
                        
                        # Parse the file to extract class/function names
                        try:
                            parsed = code_parser.parse_file(Path(fp))
                            classes = [c.get("name", "") for c in parsed.get("classes", []) if c.get("name")]
                            functions = [f.get("name", "") for f in parsed.get("functions", []) if f.get("name")]
                            
                            detail_parts = []
                            if classes:
                                detail_parts.append(f"Classes: {', '.join(classes)}")
                            if functions:
                                detail_parts.append(f"Functions: {', '.join(functions)}")
                            
                            if detail_parts:
                                enriched_map_lines.append(f"- {rel} → {' | '.join(detail_parts)}")
                            else:
                                enriched_map_lines.append(f"- {rel}")
                        except Exception:
                            enriched_map_lines.append(f"- {rel}")

                    enriched_map_string = "\n".join(enriched_map_lines)

                    blueprint_prompt = (
                        "You are a Principal Software Architect. I am giving you the complete file map of a project "
                        "WITH the actual class names and function names extracted from each file's AST.\n"
                        "Your job is to build a highly condensed \"Master Routing Blueprint\" for future AI agents.\n\n"
                        "CRITICAL RULES:\n"
                        "1. READ the class and function names carefully — they tell you EXACTLY what each file does. "
                        "Do NOT guess or assume the project type from filenames alone.\n"
                        "2. Group files into logical architectural domains based on the ACTUAL code structures.\n"
                        "3. For each domain, write exactly one sentence explaining its purpose and data flow.\n"
                        "4. List the 2-3 most critical files in that domain.\n"
                        "5. DO NOT use conversational filler. Output ONLY a strict, token-efficient Markdown list.\n\n"
                        f"Enriched File Map (with AST structures):\n{enriched_map_string}"
                    )

                    _bp_kwargs = {"num_ctx": 16384}
                    if is_local:
                        _bp_kwargs["api_base"] = "http://localhost:11434"
                    else:
                        _bp_kwargs["api_key"] = user_api_key
                    response = litellm.completion(
                        model=selected_model,
                        messages=[{"role": "user", "content": blueprint_prompt}],
                        **_bp_kwargs
                    )
                    st.session_state.retained_memory = response.choices[0].message.content
                    st.warning("⚠️ Master Blueprint injected! The AI will now use this Memory Bank as its absolute source of truth, overriding local chat confusion.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Blueprint Error: {e}")

    # Text area bound to session state
    st.session_state.retained_memory = st.text_area(
        "Crucial Facts & Context:", 
        value=st.session_state.retained_memory, 
        height=200
    )

    if st.button("🧹 Clear Chat History (Keep Memory)"):
        st.session_state.messages = []
        st.rerun()

# ---------------------------------------------------------------------------
# Main Interface: Chat
# ---------------------------------------------------------------------------
st.title("🔮 Lokr")
st.caption("Privacy-first Graph-RAG code intelligence, powered by your local GPU.")

# Display Chat History
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Quick Actions for Vibe Coders
prompt_to_send = None
if st.session_state.indexed_path:
    st.markdown("### ⚡ Quick Actions for Vibe Coders")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    if col1.button("🚀 Explain Project (ELI5)"):
        prompt_to_send = "I am a vibe coder. Explain this entire project to me simply. What is the ultimate goal, what does it do, and how do the main pieces talk to each other without using overly complex code jargon? CRITICAL INSTRUCTION: You MUST look at the Global Project File Map to understand the full scope of the architecture. You are explicitly allowed and encouraged to reference and explain files from the Global Map even if their raw source code is not provided in the Deep-Dive Context."
        
    if col2.button("🛠️ Deep Tech Stack"):
        prompt_to_send = "Analyze the project and give me the exact tech stack. Don't just list languages—identify the specific frameworks, libraries, and architectural patterns (e.g., REST API, WebSockets, Neural Networks, MCTS) used."
        
    if col3.button("📚 Study Guide & Concepts"):
        prompt_to_send = "I want to work on this project but I don't know the underlying math or syntax. Give me a 'Study Guide'. What exact high-level concepts, algorithms, or YouTube search terms should I look up so I know how to prompt AI to modify this?"

    if col4.button("🗜️ Compress Chat"):
        if len(st.session_state.messages) > 0:
            with st.spinner("Summarizing chat..."):
                history_text = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
                summary_prompt = f"Summarize the following conversation into concise bullet points focusing ONLY on architectural decisions, bugs found, or goals. Ignore conversational filler.\n\n{history_text}"
                
                _cmp_kwargs = {"num_ctx": 16384}
                if is_local:
                    _cmp_kwargs["api_base"] = "http://localhost:11434"
                else:
                    _cmp_kwargs["api_key"] = user_api_key
                response = litellm.completion(
                    model=selected_model,
                    messages=[{"role": "user", "content": summary_prompt}],
                    **_cmp_kwargs
                )
                new_summary = response.choices[0].message.content
                st.session_state.retained_memory += f"\n\n{new_summary}"
                st.session_state.messages = []
                st.rerun()

    if col5.button("🤖 Auto-Coder Prompt"):
        # Find the last assistant message (the diagnosis)
        last_diagnosis = None
        for m in reversed(st.session_state.messages):
            if m["role"] == "assistant":
                last_diagnosis = m["content"]
                break
        
        if not last_diagnosis:
            st.warning("Please ask the Oracle to diagnose an issue first.")
        else:
            with st.spinner("🤖 Generating structured prompt for your coding agent..."):
                # Build the Global File Map for accurate file paths
                p_path = Path(st.session_state.indexed_path)
                file_map_lines = []
                for fp in st.session_state.active_files:
                    try:
                        file_map_lines.append(f"- {Path(fp).relative_to(p_path)}")
                    except ValueError:
                        file_map_lines.append(f"- {Path(fp).name}")
                file_map_for_prompt = "\n".join(file_map_lines)

                meta_system = (
                    "You are a Master Prompt Engineer. The user will provide a bug diagnosis. "
                    "Your job is to convert this diagnosis into a STRICT, structured prompt for an AI Coding Agent.\n"
                    "You MUST output ONLY the raw prompt inside a markdown code block so the user can copy-paste it.\n\n"
                    "Use this exact XML/Structured format:\n"
                    "<task>\n[1 sentence objective]\n</task>\n"
                    "<context>\n[Summarize the diagnosis and what is wrong]\n</context>\n"
                    "<files_to_edit>\n[List the exact files that need to be changed. "
                    "You MUST ONLY use paths from the PROJECT FILE MAP below. Do NOT invent paths.]\n</files_to_edit>\n"
                    "<instructions>\n1. [Specific coding step]\n2. [Specific coding step]\n</instructions>\n"
                    "<strict_rules>\n- DO NOT hallucinate new imports.\n- ONLY output the modified code blocks.\n</strict_rules>\n\n"
                    f"### PROJECT FILE MAP (Use ONLY these paths):\n{file_map_for_prompt}"
                )

                _ac_kwargs = {"num_ctx": 16384}
                if is_local:
                    _ac_kwargs["api_base"] = "http://localhost:11434"
                else:
                    _ac_kwargs["api_key"] = user_api_key
                response = litellm.completion(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": meta_system},
                        {"role": "user", "content": f"Here is the bug diagnosis:\n\n{last_diagnosis}"}
                    ],
                    **_ac_kwargs
                )
                generated_prompt = response.choices[0].message.content
                st.subheader("📋 Auto-Coder Prompt (Copy & Paste)")
                st.code(generated_prompt, language="markdown")


# Chat Input & Agent Logic
user_input = st.chat_input("Ask about the codebase...")
if user_input:
    prompt_to_send = user_input
    
    # --- Prompt Defense ---
    system_tokens = ["STRICT RAG DIRECTIVES", "Expert DevOps AI", "Principal Software Architect"]
    if any(token in prompt_to_send for token in system_tokens):
        st.warning("⚠️ **System Prompt Detected:** It looks like you're pasting system-level instructions into the chat. Our engine already handles these! Please stick to asking questions to avoid confusing the AI.")

if prompt_to_send:
    # Limit chat history to last 4 messages (Long-term handled by Memory Bank)
    if len(st.session_state.messages) > 4:
        st.session_state.messages = st.session_state.messages[-4:]

    # --- Cloud API Key Validation ---
    if not is_local and not user_api_key.strip():
        with st.chat_message("assistant"):
            st.error("☁️ **Cloud API Key Required:** You selected Cloud API mode but have not entered an API key. "
                     "Please paste your key in the 🔑 API Key field in the sidebar.")
        st.stop()

    # 1. Display User Message
    st.session_state.messages.append({"role": "user", "content": prompt_to_send})
    with st.chat_message("user"):
        st.markdown(prompt_to_send)

    # 2. Check Prerequisites
    if not st.session_state.indexed_path:
        error_msg = "Please index a project in the sidebar before asking questions."
        with st.chat_message("assistant"):
            st.error(error_msg)
        st.session_state.messages.append({"role": "assistant", "content": error_msg})
        st.stop()

    # 3. Smart Query Router: Memory-First or Full RAG
    with st.chat_message("assistant"):
        # --- Memory-First Detection ---
        memory_keywords = ["remember", "memory", "recall", "what do you know", "what have we discussed", "what did we", "summary so far"]
        query_lower = prompt_to_send.lower()
        is_memory_query = any(kw in query_lower for kw in memory_keywords)

        if is_memory_query and st.session_state.retained_memory.strip():
            # ⚡ FAST PATH: Answer from Memory Bank only (skip RAG)
            with st.spinner("🧠 Checking Memory Bank..."):
                try:
                    p_path = Path(st.session_state.indexed_path)
                    rel_paths = []
                    for fp in st.session_state.active_files:
                        try:
                            rel_paths.append(f"- {Path(fp).relative_to(p_path)}")
                        except ValueError:
                            rel_paths.append(f"- {Path(fp).name}")
                    file_map_str = "\n".join(rel_paths)

                    messages_payload = [
                        {
                            "role": "system",
                            "content": (
                                "You are an Expert DevOps AI and Principal Software Architect.\n\n"
                                "The user is asking about what you remember or know. "
                                "Answer ONLY from the RETAINED MEMORY and GLOBAL FILE MAP below. "
                                "Do NOT make up information. If the Memory Bank is empty, say so.\n\n"
                                "### 🧠 RETAINED MEMORY (Crucial User-Defined Context):\n"
                                f"{st.session_state.retained_memory}\n\n"
                                "### 📂 GLOBAL PROJECT FILE MAP:\n"
                                f"{file_map_str}"
                            )
                        }
                    ] + [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages
                    ]

                    _mem_kwargs = {"num_ctx": 16384}
                    if is_local:
                        _mem_kwargs["api_base"] = "http://localhost:11434"
                    else:
                        _mem_kwargs["api_key"] = user_api_key
                    response = litellm.completion(
                        model=selected_model,
                        messages=messages_payload,
                        **_mem_kwargs
                    )

                    ai_response = response.choices[0].message.content
                    st.markdown(ai_response)
                    st.session_state.messages.append({"role": "assistant", "content": ai_response})

                except Exception as e:
                    err_text = f"❌ Error: {str(e)}"
                    st.error(err_text)
                    st.session_state.messages.append({"role": "assistant", "content": err_text})

        else:
            # 🔍 FULL RAG PATH: Consult the Oracle
            with st.spinner("🔍 Oracle is consulting the graph..."):
                try:
                    # Setup components
                    p_path = Path(st.session_state.indexed_path)
                    code_parser = CodeParser()
                    v_db = CodebaseVectorDB(db_dir=str(p_path / "data" / "vector_store") if (p_path / "data").exists() else "data/vector_store")
                    graph = DependencyGraph()
                    
                    # Build Graph (Restricted to Active Files)
                    graph.build_graph(file_paths=st.session_state.active_files, parser=code_parser)
                    
                    # Generate Context (With File Filter)
                    oracle = ContextOracle(parser=code_parser, graph=graph, db=v_db)
                    context = oracle.generate_context(query=prompt_to_send, top_k=5, allowed_files=st.session_state.active_files)
                    with st.expander("🕵️‍♂️ See What the AI is Reading (Debug RAG)"):
                        st.text("Here is the exact text the Oracle retrieved from your files:")
                        st.code(context, language="markdown")
                    
                    # Generate Global File Map (Restricted to Active Files)
                    rel_paths = []
                    for fp in st.session_state.active_files:
                        try:
                            rel_paths.append(f"- {Path(fp).relative_to(p_path)}")
                        except ValueError:
                            rel_paths.append(f"- {Path(fp).name}")
                    file_map_str = "\n".join(rel_paths)

                    # 4. Prepare Payload for LiteLLM (Ollama)
                    messages_payload =[
                        {
                            "role": "system",
                            "content": (
                                "You are an Expert DevOps AI and Principal Software Architect.\n\n"
                                "### 🧠 RETAINED MEMORY (Crucial User-Defined Context):\n"
                                f"{st.session_state.retained_memory}\n\n"
                                "### 📂 GLOBAL PROJECT FILE MAP:\n"
                                f"{file_map_str}\n\n"
                                "### 🔬 DEEP-DIVE CONTEXT (Raw Source Code & Dependencies):\n"
                                f"{context}\n\n"
                                "### ⚠️ STRICT RAG DIRECTIVES (CRITICAL):\n"
                                "1. You MUST answer the user's specific questions using ONLY the provided DEEP-DIVE CONTEXT.\n"
                                "2. Do NOT hallucinate or generate generic boilerplate code. Do NOT rely on your internal training data for specific logic.\n"
                                "3. If you quote code, it must be an exact match from the provided text.\n"
                                "4. If the exact answer to a specific question is not in the provided text, you MUST explicitly say: 'I cannot find this in the context.'\n\n"
                                "### 🧠 ARCHITECTURAL REASONING FRAMEWORK (For General Summaries ONLY):\n"
                                "If the user asks for a general project overview, use the Global File Map to outline Project Classification, Tech Stack, Core Architecture Breakdown, and Key Entry Points. For specific logic questions, strictly follow the RAG directives above."
                            )
                        }
                    ] + [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages
                    ]
                    
                    # 5. Call Local Model (With expanded context window)
                    # Build dynamic kwargs based on execution mode
                    _llm_kwargs = {"num_ctx": 16384}
                    if is_local:
                        _llm_kwargs["api_base"] = "http://localhost:11434"
                    else:
                        _llm_kwargs["api_key"] = user_api_key
                    response = litellm.completion(
                        model=selected_model,
                        messages=messages_payload,
                        **_llm_kwargs
                    )
                    
                    ai_response = response.choices[0].message.content
                    
                    # --- Reasoning Extraction (Polyglot AI Support) ---
                    import json
                    reasoning = ""
                    content_to_show = ai_response
                    
                    # Format 1: DeepSeek-R1 <think> tags
                    if "<think>" in ai_response and "</think>" in ai_response:
                        parts = ai_response.split("</think>")
                        reasoning = parts[0].replace("<think>", "").strip()
                        content_to_show = parts[1].strip()
                    else:
                        # Format 2: JSON Object (Some Ollama Models)
                        try:
                            start_idx = ai_response.find("{")
                            end_idx = ai_response.rfind("}")
                            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                                json_str = ai_response[start_idx:end_idx+1]
                                parsed = json.loads(json_str)
                                if isinstance(parsed, dict) and "reasoning" in parsed and "content" in parsed:
                                    reasoning = parsed["reasoning"]
                                    content_to_show = parsed["content"]
                        except Exception:
                            pass
                    
                    if reasoning:
                        with st.expander("💭 Reasoning Process", expanded=False):
                            st.info(reasoning)

                    st.markdown(content_to_show)
                    st.session_state.messages.append({"role": "assistant", "content": ai_response})

                except Exception as e:
                    err_text = f"❌ Error: {str(e)}"
                    st.error(err_text)
                    st.session_state.messages.append({"role": "assistant", "content": err_text})

