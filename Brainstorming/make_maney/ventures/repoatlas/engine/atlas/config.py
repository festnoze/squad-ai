"""Engagement configuration and shared constants."""

import json
import os

# Directories never scanned (vendored, generated, tooling caches)
DEFAULT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "bower_components",
    "venv", ".venv", "env", ".tox", "__pycache__", ".pytest_cache",
    ".mypy_cache", "htmlcov", "dist", "build", "out", "target",
    "bin", "obj", "packages", ".idea", ".vs", ".vscode",
    "coverage", "vendor", ".angular", ".next", ".nuxt", ".godot",
}

GENERATED_FILE_SUFFIXES = (
    ".min.js", ".min.css", ".map", ".designer.cs", ".g.cs",
    ".generated.cs", ".d.ts", ".pyc", ".uid",
)

GENERATED_FILE_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "uv.lock", "composer.lock", "Cargo.lock", "Pipfile.lock",
}

LANG_BY_EXT = {
    ".py": "python",
    ".cs": "csharp",
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".html": "markup", ".cshtml": "markup", ".razor": "markup",
    ".css": "style", ".scss": "style", ".less": "style",
    ".json": "data", ".yml": "data", ".yaml": "data", ".toml": "data",
    ".xml": "data", ".csproj": "data", ".sln": "data",
    ".md": "docs", ".rst": "docs",
    ".sql": "sql", ".sh": "shell", ".ps1": "shell", ".bat": "shell",
}

# Languages whose files feed scanners and module mapping
CODE_LANGS = {"python", "csharp", "typescript", "javascript"}


class RepoConfig:
    def __init__(self, data):
        self.name = data["name"]
        self.path = data["path"]
        self.stack_hint = data.get("stack")  # optional override

    def as_dict(self):
        return {"name": self.name, "path": self.path, "stack": self.stack_hint}


class Engagement:
    """One client engagement: N repos, an output dir, and options."""

    def __init__(self, data, base_dir="."):
        self.name = data.get("name", "engagement")
        self.language = data.get("language", "en")
        base = data.get("base_dir", base_dir)
        self.repos = [RepoConfig(r) for r in data.get("repos", [])]
        for repo in self.repos:
            if not os.path.isabs(repo.path):
                repo.path = os.path.normpath(os.path.join(base, repo.path))
        self.out_dir = data.get("out", os.path.join(base, "atlas_out", self.name))
        self.work_dir = data.get("work", os.path.join(self.out_dir, "work"))
        self.exclude_dirs = set(DEFAULT_EXCLUDE_DIRS) | set(data.get("exclude_dirs", []))
        llm = data.get("llm", {})
        self.llm_enabled = bool(llm.get("enabled", False))
        self.llm_model = llm.get("model")  # None = CLI default
        self.max_modules = int(data.get("max_modules", 20))

    def repo(self, name):
        for repo in self.repos:
            if repo.name == name:
                return repo
        raise KeyError(f"unknown repo '{name}' (have: {[r.name for r in self.repos]})")


def load_engagement(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return Engagement(data, base_dir=os.path.dirname(os.path.abspath(path)))
