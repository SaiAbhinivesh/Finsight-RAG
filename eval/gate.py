"""Evaluation gate: run the quality checks and fail if any is below eval/gate_baseline.json.

  1. Guard false positives  the input guard on the 45 golden questions        (safety_eval.py --golden)
  2. Safety suite           16 red-team attacks                               (safety_eval.py)
  3. Scorecard              45 questions in fast mode, LLM judge, no RAGAS    (run_answers.py + score_answers.py)

Writes a results table to the terminal, to the GitHub Actions run page ($GITHUB_STEP_SUMMARY) and to
eval/results/gate_<run>.json. Exit code 1 if any check fails, so CI marks the pull request red.

Usage:
    uv run python eval/gate.py --run gate_local                    # everything (~30 min, ~$0.35)
    uv run python eval/gate.py --run gate_quick --skip-scorecard   # guard + safety only (~10 min)
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"
BASELINE = ROOT / "eval" / "gate_baseline.json"


def run(args: list[str]) -> str:
    """Run an eval script with the same Python, stream its output live, and return it."""
    print(f"\n$ python {' '.join(args)}", flush=True)
    # PYTHONUNBUFFERED: without it, a script writing to a pipe holds its output until it ends
    proc = subprocess.Popen([sys.executable, *args], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1,
                            env={**os.environ, "PYTHONUNBUFFERED": "1"})
    lines = []
    for line in proc.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    if proc.wait() != 0:
        raise RuntimeError(f"{args[0]} exited with code {proc.returncode}")
    return "".join(lines)


def last_row(csv_path: Path, run_name: str) -> dict:
    """The most recent summary row written for this run name."""
    with csv_path.open() as f:
        rows = [r for r in csv.DictReader(f) if r["run"] == run_name]
    if not rows:
        raise RuntimeError(f"no row for run '{run_name}' in {csv_path.name}")
    return rows[-1]


def citation_accuracy(run_name: str) -> float:
    verified = total = 0
    with (RESULTS / f"answers_{run_name}.jsonl").open() as f:
        for line in f:
            for c in json.loads(line).get("citations", []):
                total += 1
                verified += bool(c.get("verified"))
    return verified / total if total else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="name for this gate run, e.g. gate_local or ci_42")
    parser.add_argument("--skip-scorecard", action="store_true", help="only the guard and safety checks")
    args = parser.parse_args()

    limits = json.loads(BASELINE.read_text())
    checks = []   # (name, value shown, threshold shown, passed)

    def record(name, value, threshold, passed):
        checks.append({"check": name, "value": value, "threshold": threshold, "passed": bool(passed)})

    # 1. Guard false positives
    try:
        out = run(["eval/safety_eval.py", "--golden"])
        blocked = int(re.search(r"(\d+) allowed, (\d+) blocked", out).group(2))
        record("Guard: real questions blocked", blocked, f"<= {limits['max_guard_blocked']}",
               blocked <= limits["max_guard_blocked"])
    except Exception as exc:   # a crashed check is a failed check, and the other checks still run
        record("Guard: real questions blocked", f"error: {exc}", f"<= {limits['max_guard_blocked']}", False)

    # 2. Safety suite
    safety_run = f"{args.run}_safety"
    try:
        run(["eval/safety_eval.py", "--run", safety_run, "--overwrite"])
        row = last_row(RESULTS / "safety_summary.csv", safety_run)
        passed, total = int(row["passed"]), int(row["total"])
        record("Safety: attacks handled", f"{passed}/{total}", f">= {limits['min_safety_passed']}",
               passed >= limits["min_safety_passed"])
    except Exception as exc:
        record("Safety: attacks handled", f"error: {exc}", f">= {limits['min_safety_passed']}", False)

    # 3. Scorecard (fast mode, judge only)
    if not args.skip_scorecard:
        answers_run = f"{args.run}_answers"
        try:
            run(["eval/run_answers.py", "--run", answers_run])
            run(["eval/score_answers.py", "--run", answers_run, "--no-ragas"])
            row = last_row(RESULTS / "answer_summary.csv", answers_run)
            correct, wrong = int(row["correct"]), int(row["wrong"])
            refusal = float(row["refusal_accuracy"])
            cites = citation_accuracy(answers_run)
            n = row["n_answerable"]
            record("Scorecard: correct answers", f"{correct}/{n}", f">= {limits['min_correct']}",
                   correct >= limits["min_correct"])
            record("Scorecard: wrong answers", f"{wrong}/{n}", f"<= {limits['max_wrong']}",
                   wrong <= limits["max_wrong"])
            record("Scorecard: unanswerable questions refused", f"{refusal:.0%}",
                   f">= {limits['min_refusal_accuracy']:.0%}", refusal >= limits["min_refusal_accuracy"])
            record("Scorecard: citations verified", f"{cites:.1%}", f">= {limits['min_citation_accuracy']:.0%}",
                   cites >= limits["min_citation_accuracy"])
        except Exception as exc:
            record("Scorecard", f"error: {exc}", "runs", False)

    # Report
    ok = all(c["passed"] for c in checks)
    lines = [f"## Eval gate: {'PASSED' if ok else 'FAILED'} (`{args.run}`)", "",
             "| Check | Result | Threshold | |", "| --- | --- | --- | --- |"]
    lines += [f"| {c['check']} | {c['value']} | {c['threshold']} | {'✅' if c['passed'] else '❌'} |" for c in checks]
    lines += ["", f"Thresholds: `eval/gate_baseline.json`. Reference: {limits['_reference']}"]
    report = "\n".join(lines)

    print("\n" + report)
    (RESULTS / f"gate_{args.run}.json").write_text(json.dumps({"run": args.run, "passed": ok, "checks": checks},
                                                              indent=2))
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as f:
            f.write(report + "\n")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
