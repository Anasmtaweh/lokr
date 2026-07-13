import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.qa_evaluator import run_lokr, verify_citations, judge_response

API_KEY = "fw_JiJxxDeDb3avbF46QqnMgm"
TARGET_DIR = Path("../pet-ai-project").resolve()

# The specific questions that previously failed
test_cases = [
    {
        "id": "Run 08 Q1 (Regex Sabotage - config.js)",
        "question": "Does the backend/config/config.js file define a getEnv helper function that reads environment variables, trims whitespace, and supports a default fallback value?",
        "expected_flag": "[FEATURE PRESENT]"
    },
    {
        "id": "Run 08 Q5 (Regex Sabotage - .env.example)",
        "question": "Does the frontend/.env.example file define a REACT_APP_API_URL environment variable for the backend API base URL?",
        "expected_flag": "[FEATURE PRESENT]"
    },
    {
        "id": "Run 04 Q1 (NLP Hallucination - Express.js)",
        "question": "Does the backend use Express.js to handle API requests?",
        "expected_flag": "[FEATURE PRESENT]"
    }
]

def main():
    if not TARGET_DIR.exists():
        print(f"Target dir {TARGET_DIR} not found.")
        return

    print("=== TESTING ARCHITECTURAL FIXES ===")
    for tc in test_cases:
        print(f"\n--- Testing: {tc['id']} ---")
        print(f"Question: {tc['question']}")
        
        # 1. Run Lokr
        print("[*] Running Lokr...")
        try:
            lokr_answer, context_md = run_lokr(tc['question'], TARGET_DIR, API_KEY)
            # Print the first line of Lokr's answer (the flag)
            print(f"Lokr Flag: {lokr_answer.splitlines()[0] if lokr_answer else 'NONE'}")
            print(f"Lokr Full Answer:\n{lokr_answer}\n")
            
            # 2. Verify Citations
            print("[*] Verifying Citations...")
            citation_report = verify_citations(lokr_answer, TARGET_DIR)
            print(f"Citation Report:\n{citation_report}\n")
            
            # 3. Judge Response
            print("[*] Judging Response...")
            score, reason = judge_response(tc['question'], tc['expected_flag'], lokr_answer, citation_report, API_KEY)
            print(f"Score: {'✅ PASS' if score == 1 else '❌ FAIL'} (Judge: {reason})")
        except Exception as e:
            print(f"Error during test: {e}")

if __name__ == '__main__':
    main()
