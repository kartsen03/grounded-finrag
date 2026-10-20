"""Paths and pinned model revisions shared across the service."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get("FINRAG_REPO_ROOT", Path(__file__).resolve().parents[3]))
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw" / "financebench"
PDF_DIR = RAW_DIR / "pdfs"
QUESTIONS_FILE = RAW_DIR / "data" / "financebench_open_source.jsonl"
DOC_INFO_FILE = RAW_DIR / "data" / "financebench_document_information.jsonl"
SPLIT_FILE = DATA_DIR / "splits" / "financebench_split_v1.json"
# Derived from the CC BY-NC PDFs, so gitignored like data/raw/.
PROCESSED_DIR = DATA_DIR / "processed"
RESULTS_DIR = REPO_ROOT / "results"

# Pinned Hugging Face revisions (commit SHAs), so tokenization and embeddings are reproducible.
EMBED_MODEL = "BAAI/bge-base-en-v1.5"
EMBED_MODEL_REVISION = "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"
RERANK_MODEL = "BAAI/bge-reranker-base"
RERANK_MODEL_REVISION = "2cfc18c9415c912f9d8155881c133215df768a70"
