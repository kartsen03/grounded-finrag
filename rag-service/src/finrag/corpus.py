"""FinanceBench questions, document metadata and the fixed dev/test split."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from finrag import config

DOC_TYPE_LABELS = {"10k": "10-K", "10k_annualreport": "10-K", "10q": "10-Q", "8k": "8-K",
                   "earnings": "Earnings release"}
_QUARTER = re.compile(r"_(\d{4})Q([1-4])_")
_DATED = re.compile(r"dated[-_](\d{4}-\d{2}-\d{2})")  # upstream names use both separators


@dataclass(frozen=True)
class DocMeta:
    doc_name: str
    company: str
    doc_type: str  # display label: 10-K, 10-Q, 8-K, Earnings release
    fiscal_year: int
    fiscal_quarter: int | None
    filing_date: str | None  # 8-Ks carry their date in the file name
    sector: str

    @property
    def period_label(self) -> str:
        if self.fiscal_quarter:
            return f"FY{self.fiscal_year} Q{self.fiscal_quarter}"
        if self.filing_date:
            return f"{self.filing_date}"
        return f"FY{self.fiscal_year}"

    @property
    def header(self) -> str:
        """Short context line prepended to every chunk before embedding."""
        return f"{self.company} {self.doc_type} {self.period_label}"


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def doc_meta_from_row(row: dict) -> DocMeta:
    name = row["doc_name"]
    quarter = _QUARTER.search(name)
    dated = _DATED.search(name)
    return DocMeta(
        doc_name=name,
        company=row["company"],
        doc_type=DOC_TYPE_LABELS[row["doc_type"].lower()],
        fiscal_year=int(quarter.group(1)) if quarter else int(row["doc_period"]),
        fiscal_quarter=int(quarter.group(2)) if quarter else None,
        filing_date=dated.group(1) if dated else None,
        sector=row["gics_sector"],
    )


@lru_cache(maxsize=1)
def questions() -> dict[str, dict]:
    return {row["financebench_id"]: row for row in read_jsonl(config.QUESTIONS_FILE)}


@lru_cache(maxsize=1)
def all_doc_meta() -> dict[str, DocMeta]:
    return {row["doc_name"]: doc_meta_from_row(row) for row in read_jsonl(config.DOC_INFO_FILE)}


def corpus_docs() -> list[DocMeta]:
    """Documents referenced by the 150 questions: the retrieval corpus."""
    meta = all_doc_meta()
    names = sorted({q["doc_name"] for q in questions().values()})
    return [meta[n] for n in names]


@lru_cache(maxsize=1)
def split() -> dict[str, list[str]]:
    data = json.loads(config.SPLIT_FILE.read_text(encoding="utf-8"))
    return {"dev": data["dev"], "test": data["test"]}


def evidence_pages(question: dict) -> set[tuple[str, int]]:
    """Gold (doc_name, 0-based page index) pairs. FinanceBench page numbers are 0-based."""
    return {(ev["doc_name"], int(ev["evidence_page_num"])) for ev in question["evidence"]}
