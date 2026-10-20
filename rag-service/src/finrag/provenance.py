"""Provenance stamped into every results file: commit, machine, versions, power plan.

No number goes into the README unless the file it comes from carries this block.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata

from finrag import config


def _run(cmd: list[str]) -> str | None:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15, cwd=config.REPO_ROOT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


CODE_PATHS = ["rag-service/src", "llm-gateway/src", "model-server", "scripts"]


def git_state() -> dict:
    """HEAD plus whether any code (tracked or not) differs from it. Data and results don't count."""
    commit = _run(["git", "rev-parse", "HEAD"])
    dirty = _run(["git", "status", "--porcelain", "--", *CODE_PATHS])
    return {"commit": commit, "dirty": bool(dirty)}


def gpu() -> str | None:
    return _run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])


def power_plan() -> str | None:
    if sys.platform != "win32":
        return None
    out = _run(["powercfg", "/getactivescheme"])
    return out.split("(")[-1].rstrip(")") if out and "(" in out else out


def versions(*packages: str) -> dict:
    found = {}
    for name in packages:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            found[name] = None
    return found


def stamp(*packages: str, **extra) -> dict:
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": git_state(),
        "machine": {
            "platform": platform.platform(),
            "cpu": platform.processor(),
            "gpu": gpu(),
            "power_plan": power_plan(),
            "python": platform.python_version(),
        },
        "packages": versions(*packages),
        **extra,
    }
