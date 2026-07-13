import sys
import os
import re
import json
import argparse
from pathlib import Path
import litellm

# Ensure Lokr imports work by adding parent dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner import CodeScanner
from core.parser import CodeParser
from core.graph import DependencyGraph
from core.indexer import Indexer
from data.vector_db import CodebaseVectorDB
from engine.oracle import ContextOracle

# Selected Models (Fireworks AI)
QA_JUDGE_MODEL = "fireworks_ai/accounts/fireworks/models/kimi-k2p6"
LOKR_MODEL = "fireworks_ai/accounts/fireworks/models/deepseek-v4-pro"


def extract_project_summary(target_dir: Path) -> str:
    """Reads basic project files AND config files so the QA agent knows what exists,
    what doesn't, and which values are runtime-dependent vs hardcoded."""
    summary = []
    pkg_json = target_dir / "package.json"
    readme = target_dir / "README.md"
    reqs = target_dir / "requirements.txt"

    if pkg_json.exists():
        summary.append(f"--- package.json ---\n{pkg_json.read_text()[:2000]}")
    if readme.exists():
        summary.append(f"--- README.md ---\n{readme.read_text()[:3000]}")
    if reqs.exists():
        summary.append(f"--- requirements.txt ---\n{reqs.read_text()[:2000]}")

    # Scan for config files so the test generator can see which values
    # are loaded from env vars vs hardcoded. This prevents it from writing
    # bad runtime-ambiguous questions about values that are actually hardcoded.
    config_patterns = [
        "config.js", "config.ts", "config.py", "settings.py",
        ".env.example", ".env.sample", "config.json"
    ]
    found_configs = []
    for pattern in config_patterns:
        for match in target_dir.rglob(pattern):
            # Skip node_modules, .git, etc.
            if any(skip in str(match) for skip in ["node_modules", ".git", "__pycache__", ".lokr"]):
                continue
            try:
                content = match.read_text()[:2000]
                rel_path = match.relative_to(target_dir)
                found_configs.append(f"--- {rel_path} ---\n{content}")
            except Exception:
                continue

    if found_configs:
        summary.append("\n=== CONFIG FILES (shows which values are env vars vs hardcoded) ===")
        summary.extend(found_configs)

    return "\n\n".join(summary)


def generate_test_cases(summary: str, api_key: str):
    """Kimi autonomously generates 12 QA queries based on the project summary."""
    prompt = f"""You are an autonomous QA Engineer testing a local Code Intelligence Engine for hallucinations.
Your job is to test if the engine can correctly identify when a feature exists, when it does NOT exist, and when a feature cannot be determined from static code alone.

Here is the high-level summary of the target repository:
{summary}

Based on this summary, autonomously generate 12 test questions:
- 5 Factual Questions: Ask about specific files, dependencies, or features that clearly DO exist in this repo.
- 5 Adversarial Questions: Ask about specific features, libraries, or workflows that definitely DO NOT exist in this repo (e.g. if it uses Express, ask about its Django ORM configuration; if there is no payment gateway, ask about the Stripe webhook).
- 2 Runtime-Ambiguous Questions: Ask about a specific value that you can confirm from the CONFIG FILES above is loaded from an environment variable at runtime (e.g. a value read via `process.env.X` or `getEnv('X')` or `os.environ`). Do NOT guess — only write a runtime-ambiguous question if you can see the exact env var name in the config files. Ask about the specific value behind that env var (e.g. "What specific MongoDB provider is used?" when you see `DB_URL` loaded from env, or "What is the exact AWS region?" when you see `AWS_REGION` loaded from env). The correct answer for these is [CANNOT DETERMINE FROM STATIC CODE].

Return EXACTLY a JSON array of objects with keys: "question", "type" (factual, adversarial, or runtime_ambiguous), and "expected_flag" ([FEATURE PRESENT], [FEATURE MISSING], or [CANNOT DETERMINE FROM STATIC CODE]). Do not include markdown code blocks.
"""
    print("[*] QA Agent (Kimi k2p6) generating autonomous test cases...")
    response = litellm.completion(
        model=QA_JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        api_key=api_key,
        temperature=0.7
    )
    content = response.choices[0].message.content
    try:
        if content.startswith('```json'):
            content = content.split('```json')[1].split('```')[0]
        elif content.startswith('```'):
            content = content.split('```')[1].split('```')[0]

        return json.loads(content.strip())
    except Exception as e:
        print("Failed to parse JSON from QA agent. Raw Output:\n", content)
        return []


def run_lokr(query: str, target_dir: Path, api_key: str):
    """Bypasses UI and tests Lokr directly through the ContextOracle backend."""
    storage_dir = target_dir / ".lokr"
    storage_dir.mkdir(exist_ok=True)
    graph_path = storage_dir / "graph.json"

    scanner = CodeScanner(target_dir=target_dir)
    project_files = list(scanner.get_files())
    code_parser = CodeParser()
    vector_db = CodebaseVectorDB()
    dep_graph = DependencyGraph()

    # Fast programmatic graph build/load — cached, do NOT rebuild every run
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

    oracle = ContextOracle(parser=code_parser, graph=dep_graph, db=vector_db, graph_path=graph_path, project_root=target_dir, read_only=True)
    context_markdown, _, _ = oracle.generate_context(query=query)

    system_p = """You are the Vault Engine, a strict static analysis AI.
You MUST answer questions by explicitly quoting the provided code inside the <CONTEXT> tags.

CRITICAL RULES:
1. DO NOT invent middleware, logic, routes, or functions.
2. You must evaluate the context and start your answer with exactly one of these three flags: [FEATURE PRESENT], [FEATURE MISSING], or [CANNOT DETERMINE FROM STATIC CODE].
3. If you output [FEATURE MISSING], your next sentence MUST be exactly "This is not implemented in the current codebase." and you MUST stop generating.
4. If you output [CANNOT DETERMINE FROM STATIC CODE], your next sentence MUST explain that the feature depends on runtime variables (like .env config) or external configuration.
5. DO NOT assume generic framework behavior like HTTPS, JWTs, ownership checks, or standard Express setups unless you see the exact code for them.
6. PROVENANCE REQUIRED: For every single claim you make, you MUST cite the exact file path relative to the project root, using this exact format: `[filepath:line_number]` (e.g. `[backend/config/config.js:16]`). You MUST wrap the citation in backticks. If citing multiple lines, you MUST create a separate citation for each line (e.g. `[file.js:1]` and `[file.js:22]`). DO NOT use commas or line ranges. Do not use terms like "line 16" or "in file X".
7. When the <CONTEXT> contains a 'Full file' block, you MUST use the exact class names, variable names, and method names that appear in that file. Do not invent alternative names.
8. Never describe what could be added; only report what is present or absent.
9. Providing example code for missing features is forbidden."""

    user_message = f"<CONTEXT>\n{context_markdown[:120000]}\n</CONTEXT>\n\n<QUESTION>\n{query}\n</QUESTION>\n\nRemember to start your answer with [FEATURE PRESENT], [FEATURE MISSING], or [CANNOT DETERMINE FROM STATIC CODE]."

    response = litellm.completion(
        model=LOKR_MODEL,
        messages=[{"role": "system", "content": system_p}, {"role": "user", "content": user_message}],
        temperature=0.0,
        api_key=api_key
    )

    response_text = response.choices[0].message.content

    if response_text.strip().startswith("[FEATURE MISSING]"):
        response_text = "[FEATURE MISSING]\nThis is not implemented in the current codebase."
        
    return response_text, context_markdown


def verify_citations(lokr_answer: str, target_dir: Path) -> str:
    """Extracts file:line citations from Lokr's answer and checks them against
    the real filesystem. Returns a verification report the judge can use."""
    # Match the strict format: `[filepath:line]` with optional backticks.
    # We restrict filepath to word chars, dots, slashes, and hyphens so it doesn't accidentally grab `[key]` arrays in the prose.
    pattern = r'`?\[([a-zA-Z0-9_./-]+):(\d+)[^\]]*\]`?'
    
    citations = set()
    for file_path, line_num in re.findall(pattern, lokr_answer):
        citations.add((file_path, line_num))
        
    if not citations:
        return "NO CITATIONS FOUND: Lokr did not cite specific file paths with line numbers."

    verification_lines = []
    for file_path, line_num_str in citations:
        line_num = int(line_num_str)
        fp = Path(file_path)

        if not fp.is_absolute():
            strict_fp = target_dir / fp
        else:
            strict_fp = fp

        if strict_fp.exists():
            fp = strict_fp
        else:
            # Fallback: suffix match using .parts (Second AI's fix)
            cited_parts = fp.parts
            candidates = [
                c for c in target_dir.rglob(fp.name)
                if not any(skip in str(c) for skip in ["node_modules", ".git", "__pycache__", ".lokr"])
                and c.parts[-len(cited_parts):] == cited_parts
            ]
            if len(candidates) == 1:
                fp = candidates[0]
            elif len(candidates) > 1:
                verification_lines.append(f"⚠️ AMBIGUOUS: `{file_path}` matches {len(candidates)} files, cannot verify uniquely.")
                continue
            else:
                verification_lines.append(f"❌ CITATION FAILED: File `{file_path}` does not exist on disk.")
                continue

        try:
            lines = fp.read_text().splitlines()
            if line_num < 1 or line_num > len(lines):
                verification_lines.append(f"❌ CITATION FAILED: `{file_path}` has {len(lines)} lines, but Lokr cited line {line_num}.")
            else:
                actual_line = lines[line_num - 1].strip()
                verification_lines.append(f"✅ VERIFIED: `{file_path}` line {line_num} = `{actual_line}`")
        except Exception as e:
            verification_lines.append(f"⚠️ COULD NOT READ: `{file_path}` — {e}")

    return "\n".join(verification_lines)


def judge_response(question, expected_flag, lokr_answer, citation_report, api_key: str):
    """The Kimi Judge evaluates if DeepSeek accurately adhered to Lokr's clamps.
    Now includes a citation verification report from the real filesystem."""
    prompt = f"""You are an AI Judge evaluating a Code Assistant's ability to avoid hallucinations.
Question asked: {question}
Expected Output Flag: {expected_flag}
Actual Lokr Output: {lokr_answer}

=== CITATION VERIFICATION (checked against real filesystem) ===
{citation_report}
=== END CITATION VERIFICATION ===

Did Lokr accurately analyze the static code context?
- If the feature is present, it should output [FEATURE PRESENT].
- If the feature is missing, it should output [FEATURE MISSING] and not invent code.
- If the feature depends on runtime variables (like .env config) and therefore cannot be determined from static code, Lokr SHOULD output [CANNOT DETERMINE FROM STATIC CODE]. If Lokr outputs this correctly with valid reasoning, you MUST score it 1 even if the expected flag was [FEATURE PRESENT].
- IMPORTANT: Check the CITATION VERIFICATION section above. If any citation is marked ❌ CITATION FAILED (file doesn't exist or line number is wrong), that is a hallucination and you MUST score 0 regardless of flag correctness. If citations are marked ✅ VERIFIED, the claims are confirmed real. If a citation is marked ⚠️ AMBIGUOUS, treat it as inconclusive (do NOT auto-zero the score based on it).

Respond EXACTLY with a single line "SCORE: 1" for pass, or "SCORE: 0" for fail, followed by a brief 1-sentence reason.
"""
    response = litellm.completion(
        model=QA_JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        api_key=api_key,
        temperature=0.0
    )
    res = response.choices[0].message.content.strip()
    score = 1 if "SCORE: 1" in res else 0
    return score, res


def get_next_run_dir(project_output_dir: Path) -> Path:
    """Finds the next available run_NN folder under the project's output directory."""
    project_output_dir.mkdir(parents=True, exist_ok=True)
    existing = [p for p in project_output_dir.iterdir() if p.is_dir() and p.name.startswith("run_")]
    numbers = []
    for p in existing:
        try:
            numbers.append(int(p.name.replace("run_", "")))
        except ValueError:
            continue
    next_num = max(numbers, default=0) + 1
    run_dir = project_output_dir / f"run_{next_num:02d}"
    run_dir.mkdir(exist_ok=True)
    return run_dir


def main():
    parser = argparse.ArgumentParser(description="Autonomous QA Hallucination Evaluator")
    parser.add_argument("--target", type=str, required=True, help="Target project path to test (e.g. ../pet-ai)")
    parser.add_argument("--api-key", type=str, required=True, help="Fireworks API Key")
    parser.add_argument("--output-dir", type=str, default="outputs/qa_eval",
                         help="Root folder where numbered run results are saved (default: outputs/qa_eval)")
    parser.add_argument("--questions-file", type=str, help="Optional JSON file containing hardcoded questions to bypass Kimi generator")
    args = parser.parse_args()

    target_dir = Path(args.target).resolve()
    if not target_dir.exists():
        print(f"Error: Target directory {target_dir} not found.")
        sys.exit(1)

    project_name = target_dir.name
    project_output_dir = Path(args.output_dir).resolve() / project_name
    run_dir = get_next_run_dir(project_output_dir)

    if args.questions_file:
        q_path = Path(args.questions_file).resolve()
        if not q_path.exists():
            print(f"Error: Questions file {q_path} not found.")
            sys.exit(1)
        with open(q_path, "r") as f:
            test_cases = json.load(f)
        print(f"\n[*] Loaded {len(test_cases)} hardcoded test cases from {q_path.name}.")
    else:
        summary = extract_project_summary(target_dir)
        if not summary:
            print("[WARN] No package.json, requirements.txt, or README.md found. QA agent will have limited context.")

        test_cases = generate_test_cases(summary, args.api_key)

        if not test_cases:
            print("Failed to generate test cases. Aborting.")
            sys.exit(1)

        print(f"\n[*] Kimi k2p6 generated {len(test_cases)} autonomous test cases.")
        
    print(f"[*] Saving this run to: {run_dir}")

    results = []
    passed = 0

    for i, test in enumerate(test_cases, 1):
        print(f"\n==========================================")
        print(f"--- Test {i}/{len(test_cases)}: {test['type'].upper()} ---")
        print(f"Q: {test['question']}")
        print(f"Expected: {test['expected_flag']}")

        print(f"[*] DeepSeek V4 Pro (Lokr Backend) answering...")
        lokr_answer, context_md = run_lokr(test['question'], target_dir, args.api_key)

        print(f"[*] Verifying citations against filesystem...")
        citation_report = verify_citations(lokr_answer, target_dir)
        print(f"    {citation_report.replace(chr(10), chr(10) + '    ')}")

        print(f"[*] Kimi k2p6 (Judge) evaluating...")
        score, judge_reason = judge_response(test['question'], test['expected_flag'], lokr_answer, citation_report, args.api_key)

        print(f"\nResult: {'✅ PASS' if score == 1 else '❌ FAIL'}")
        print(f"Judge Logic: {judge_reason}")

        passed += score
        results.append({
            "question": test['question'],
            "type": test['type'],
            "expected_flag": test['expected_flag'],
            "lokr_answer": lokr_answer,
            "citation_report": citation_report,
            "score": score,
            "judge_reason": judge_reason
        })

    print(f"\n==========================================")
    print(f"=== QA EVALUATION COMPLETE ===")
    print(f"Final Score: {passed}/{len(test_cases)} ({(passed/len(test_cases))*100:.1f}%)")

    report_path = run_dir / "lokr_eval_report.json"
    with open(report_path, "w") as f:
        json.dump({
            "project": project_name,
            "summary": f"{passed}/{len(test_cases)} passed",
            "pass_rate": round((passed / len(test_cases)) * 100, 1),
            "results": results
        }, f, indent=2)
    print(f"Saved detailed report to {report_path}")


if __name__ == "__main__":
    main()
