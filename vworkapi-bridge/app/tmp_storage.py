from __future__ import annotations

import os
import re
from pathlib import Path

_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_name(s: str) -> str:
    return _SAFE_RE.sub("_", s)[:64]


class TmpStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def allocate(self, msg_id: str) -> Path:
        name = _safe_name(msg_id) + ".jpg"
        return self.root / name

    def cleanup(self, path: Path) -> None:
        try:
            if path.exists():
                os.remove(path)
        except Exception:
            pass  # leave behind; cron/manual cleanup if needed
