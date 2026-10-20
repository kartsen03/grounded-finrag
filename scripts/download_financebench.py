"""Download the FinanceBench open-source sample, pinned to one upstream commit.

FinanceBench (Islam et al., 2023, arXiv:2311.11944) is published by Patronus AI
under CC BY-NC 4.0. Files are written under data/raw/financebench/ (gitignored)
and never committed. Each file is verified against the SHA-256 digest recorded
in data/financebench_manifest.json, which is committed.

    python scripts/download_financebench.py                   # download and verify
    python scripts/download_financebench.py --write-manifest  # create the manifest

--write-manifest first checks every downloaded file against its git blob hash in
the pinned commit's tree (GitHub API), so the recorded digests describe that
commit, not just whatever the first download returned.

Downloads: the two metadata JSONL files, plus one PDF for each document that
the 150 questions reference. Standard library only, so it runs before any
project dependencies are installed.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "patronus-ai/financebench"
COMMIT = "cc39aeb4afdf33909ee1412188bf89035950c2eb"  # main as of 2024-12-03 (PR #10)
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/"
TREE_API = f"https://api.github.com/repos/{REPO}/git/trees/{COMMIT}?recursive=1"
QUESTIONS = "data/financebench_open_source.jsonl"
DOC_INFO = "data/financebench_document_information.jsonl"
USER_AGENT = "grounded-finrag-downloader"

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "raw" / "financebench"
DEFAULT_MANIFEST = ROOT / "data" / "financebench_manifest.json"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    """Hash a file the way git stores it: sha1(b"blob <size>\\0" + content)."""
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def http_get(url: str, timeout: float = 60.0):
    headers = {"User-Agent": USER_AGENT}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)


def download(rel_path: str, dest: Path, attempts: int = 4) -> None:
    """Stream one file of the pinned commit to dest, replacing it atomically."""
    url = RAW_BASE + urllib.parse.quote(rel_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, attempts + 1):
        fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=dest.name + ".", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as out, http_get(url) as resp:
                while block := resp.read(1 << 20):
                    out.write(block)
            os.replace(tmp_name, dest)
            return
        except OSError as exc:  # URLError, HTTPError and socket errors are all OSError
            Path(tmp_name).unlink(missing_ok=True)
            client_error = isinstance(exc, urllib.error.HTTPError) and 400 <= exc.code < 500 and exc.code != 429
            if client_error or attempt == attempts:
                raise RuntimeError(f"download failed for {url}: {exc}") from exc
            time.sleep(2**attempt)


def fetch_git_tree() -> dict[str, tuple[str, int]]:
    """Map path -> (git blob sha1, size) for every file in the pinned commit."""
    with http_get(TREE_API) as resp:
        tree = json.load(resp)
    if tree.get("truncated"):
        raise RuntimeError("GitHub returned a truncated tree; cannot verify blob hashes")
    return {e["path"]: (e["sha"], e["size"]) for e in tree["tree"] if e["type"] == "blob"}


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("commit") != COMMIT:
        raise SystemExit(f"{path} was written for commit {manifest.get('commit')}, script pins {COMMIT}")
    return manifest


def ensure_file(rel_path: str, out_dir: Path, expected: dict | None) -> tuple[str, str, int, str]:
    """Make sure out_dir/rel_path exists with the expected digest.

    Returns (rel_path, sha256, size, status) where status is "cached", "downloaded"
    or "new" (no manifest entry yet; the caller decides whether that is allowed).
    """
    dest = out_dir / rel_path
    if expected and dest.exists() and dest.stat().st_size == expected["bytes"]:
        if sha256_of(dest) == expected["sha256"]:
            return rel_path, expected["sha256"], expected["bytes"], "cached"
    download(rel_path, dest)
    digest, size = sha256_of(dest), dest.stat().st_size
    if expected is None:
        return rel_path, digest, size, "new"
    if digest != expected["sha256"] or size != expected["bytes"]:
        dest.unlink()
        raise RuntimeError(f"checksum mismatch for {rel_path}: got {digest}, manifest has {expected['sha256']}")
    return rel_path, digest, size, "downloaded"


def check_against_tree(rel_path: str, out_dir: Path, tree: dict[str, tuple[str, int]]) -> None:
    dest = out_dir / rel_path
    if rel_path not in tree:
        raise RuntimeError(f"{rel_path} is not in commit {COMMIT}")
    blob_sha, size = tree[rel_path]
    if dest.stat().st_size != size or git_blob_sha1(dest) != blob_sha:
        raise RuntimeError(f"{rel_path} does not match its git blob {blob_sha} in commit {COMMIT}")
    if rel_path.endswith(".pdf"):
        with dest.open("rb") as f:
            if f.read(5) != b"%PDF-":
                raise RuntimeError(f"{rel_path} is not a PDF (Git LFS pointer or HTML error page?)")


def referenced_docs(questions_path: Path) -> list[str]:
    with questions_path.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    names = {row["doc_name"] for row in rows}
    names.update(ev["doc_name"] for row in rows for ev in row["evidence"])
    return sorted(names)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download the pinned FinanceBench open-source sample.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--write-manifest", action="store_true",
                        help="record SHA-256 digests for files missing from the manifest, after "
                             "checking them against the pinned commit's git tree")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest) if args.manifest.exists() else None
    if manifest is None and not args.write_manifest:
        raise SystemExit(f"{args.manifest} not found. Run once with --write-manifest to create it.")
    known: dict[str, dict] = dict(manifest["files"]) if manifest else {}
    tree = fetch_git_tree() if args.write_manifest else None

    def settle(results: list[tuple[str, str, int, str]]) -> None:
        for rel_path, digest, size, status in results:
            if status == "new":
                if tree is None:
                    raise SystemExit(f"{rel_path} is not in the manifest. Re-run with --write-manifest.")
                check_against_tree(rel_path, args.out, tree)
                known[rel_path] = {"sha256": digest, "bytes": size}
            elif tree is not None:
                check_against_tree(rel_path, args.out, tree)

    results = [ensure_file(rel, args.out, known.get(rel)) for rel in (QUESTIONS, DOC_INFO)]
    settle(results)

    docs = referenced_docs(args.out / QUESTIONS)
    pdf_paths = [f"pdfs/{name}.pdf" for name in docs]
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        pdf_results = list(pool.map(lambda rel: ensure_file(rel, args.out, known.get(rel)), pdf_paths))
    settle(pdf_results)
    results += pdf_results

    if args.write_manifest:
        payload = {
            "dataset": "FinanceBench open-source sample",
            "license": "CC BY-NC 4.0",
            "repo": REPO,
            "commit": COMMIT,
            "files": dict(sorted(known.items())),
        }
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")

    statuses: dict[str, int] = {}
    for *_, status in results:
        statuses[status] = statuses.get(status, 0) + 1
    total_bytes = sum(size for _, _, size, _ in results)
    with (args.out / QUESTIONS).open(encoding="utf-8") as f:
        n_questions = sum(1 for line in f if line.strip())
    print(f"commit {COMMIT}")
    print(f"questions: {n_questions}  referenced documents: {len(docs)}  files: {len(results)}  "
          f"bytes: {total_bytes}")
    print("status: " + ", ".join(f"{k}={v}" for k, v in sorted(statuses.items())))
    print("all files match " + ("the pinned git tree and the new manifest" if tree is not None
                                else f"{args.manifest.name}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
