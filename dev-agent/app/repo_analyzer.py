from __future__ import annotations

from pathlib import Path


class RepoAnalyzer:
    EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", "venv", "dist", "build"}
    KEY_FILES = (
        "README.md",
        "README",
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
    )

    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path)

    def get_structure(self, max_depth: int = 3) -> str:
        lines = [f"{self.repo_path.name}/"]

        def walk(current: Path, depth: int, prefix: str) -> None:
            if depth >= max_depth:
                return

            entries = sorted(current.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            for entry in entries:
                if entry.name in self.EXCLUDED_DIRS:
                    continue

                label = f"{entry.name}/" if entry.is_dir() else entry.name
                lines.append(f"{prefix}{label}")
                if entry.is_dir():
                    walk(entry, depth + 1, f"{prefix}  ")

        walk(self.repo_path, depth=0, prefix="")
        return "\n".join(lines)

    def get_key_files(self) -> dict[str, str]:
        key_files: dict[str, str] = {}
        for relative_path in self.KEY_FILES:
            file_path = self.repo_path / relative_path
            if not file_path.is_file():
                continue
            if file_path.stat().st_size > 50 * 1024:
                continue
            key_files[relative_path] = file_path.read_text(encoding="utf-8", errors="ignore")
        return key_files
