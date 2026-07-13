import json
import argparse
import statistics
from pathlib import Path


def load_runs(project_output_dir: Path):
    runs = []
    for run_dir in sorted(project_output_dir.glob("run_*")):
        report_path = run_dir / "lokr_eval_report.json"
        if report_path.exists():
            with open(report_path) as f:
                data = json.load(f)
                data["_run_dir"] = run_dir.name
                runs.append(data)
    return runs


def aggregate(runs):
    all_results = []
    per_run_rates = []

    for run in runs:
        results = run["results"]
        all_results.extend(results)
        rate = sum(r["score"] for r in results) / len(results) * 100
        per_run_rates.append(round(rate, 1))

    total = len(all_results)
    total_passed = sum(r["score"] for r in all_results)
    overall_rate = round((total_passed / total) * 100, 1) if total else 0.0

    by_type = {}
    for r in all_results:
        t = r["type"]
        by_type.setdefault(t, {"passed": 0, "total": 0})
        by_type[t]["total"] += 1
        by_type[t]["passed"] += r["score"]

    type_breakdown = {
        t: {
            "passed": v["passed"],
            "total": v["total"],
            "pass_rate": round((v["passed"] / v["total"]) * 100, 1) if v["total"] else 0.0
        }
        for t, v in by_type.items()
    }

    variance_note = None
    if len(per_run_rates) >= 2:
        stdev = round(statistics.stdev(per_run_rates), 1)
        variance_note = f"Run-to-run pass rate ranged {min(per_run_rates)}%-{max(per_run_rates)}% (stdev {stdev} pts) across {len(runs)} runs."

    return {
        "num_runs": len(runs),
        "total_questions": total,
        "total_passed": total_passed,
        "overall_pass_rate": overall_rate,
        "per_run_pass_rates": per_run_rates,
        "variance_note": variance_note,
        "breakdown_by_type": type_breakdown
    }


def main():
    parser = argparse.ArgumentParser(description="Aggregate multiple QA evaluator runs for one project")
    parser.add_argument("--project-dir", type=str, required=True,
                         help="Path to outputs/qa_eval/<project_name>")
    args = parser.parse_args()

    project_output_dir = Path(args.project_dir).resolve()
    if not project_output_dir.exists():
        print(f"Error: {project_output_dir} not found.")
        return

    runs = load_runs(project_output_dir)
    if not runs:
        print(f"No runs found in {project_output_dir}. Run qa_evaluator.py at least twice first.")
        return

    summary = aggregate(runs)

    print("=== AGGREGATE QA RESULTS ===")
    print(f"Project folder: {project_output_dir.name}")
    print(f"Runs found: {summary['num_runs']}")
    print(f"Total questions across all runs: {summary['total_questions']}")
    print(f"Overall pass rate: {summary['total_passed']}/{summary['total_questions']} ({summary['overall_pass_rate']}%)")
    if summary["variance_note"]:
        print(summary["variance_note"])
    print("\nBreakdown by question type:")
    for t, v in summary["breakdown_by_type"].items():
        print(f"  {t}: {v['passed']}/{v['total']} ({v['pass_rate']}%)")

    out_path = project_output_dir / "aggregate_summary.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved aggregate summary to {out_path}")


if __name__ == "__main__":
    main()
