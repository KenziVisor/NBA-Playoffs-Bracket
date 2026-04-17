from __future__ import annotations

import sys
from pathlib import Path


def project_root(module_file: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(module_file).resolve().parent.parent
