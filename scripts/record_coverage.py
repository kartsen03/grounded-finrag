"""Run both services' test suites with coverage and record the numbers in results/ci/coverage.json.

    python scripts/record_coverage.py

rag-service: pytest + pytest-cov (line coverage of src/finrag).
llm-gateway: mvnw verify + JaCoCo (line coverage). Needs Docker for the Testcontainers tests.
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAG = ROOT / "rag-service"
GW = ROOT / "llm-gateway"
sys.path.insert(0, str(RAG / "src"))
from finrag import provenance  # noqa: E402


def python_coverage() -> dict:
    py = RAG / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    out = subprocess.run([str(py), "-m", "pytest", "-q", "-p", "no:warnings", "--cov=finrag", "--cov-report=json"],
                         cwd=RAG, capture_output=True, text=True)
    summary = re.search(r"(\d+) passed", out.stdout)
    failed = re.search(r"(\d+) failed", out.stdout)
    totals = json.loads((RAG / "coverage.json").read_text(encoding="utf-8"))["totals"]
    return {"tests": int(summary.group(1)) if summary else 0, "failed": int(failed.group(1)) if failed else 0,
            "line_coverage_percent": round(totals["percent_covered"], 2),
            "lines_covered": totals["covered_lines"], "lines_total": totals["num_statements"],
            "tool": "pytest-cov (src/finrag)"}


def java_coverage() -> dict:
    mvnw = GW / ("mvnw.cmd" if os.name == "nt" else "mvnw")
    subprocess.run([str(mvnw), "-q", "-B", "verify", "-Djar.skip=true", "-Dspring-boot.repackage.skip=true"],
                   cwd=GW, capture_output=True, text=True, shell=os.name == "nt")
    tests = failed = 0
    for report in (GW / "target" / "surefire-reports").glob("*.txt"):
        m = re.search(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+)", report.read_text(encoding="utf-8"))
        if m:
            tests += int(m.group(1))
            failed += int(m.group(2)) + int(m.group(3))
    rows = list(csv.DictReader((GW / "target" / "site" / "jacoco" / "jacoco.csv").open(encoding="utf-8")))
    missed = sum(int(r["LINE_MISSED"]) for r in rows)
    covered = sum(int(r["LINE_COVERED"]) for r in rows)
    return {"tests": tests, "failed": failed, "line_coverage_percent": round(100 * covered / (covered + missed), 2),
            "lines_covered": covered, "lines_total": covered + missed, "tool": "JaCoCo 0.8.15"}


def main() -> int:
    payload = {**provenance.stamp(step="coverage"), "rag_service": python_coverage(), "llm_gateway": java_coverage()}
    out = ROOT / "results" / "ci" / "coverage.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: payload[k] for k in ("rag_service", "llm_gateway")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
