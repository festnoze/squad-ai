"""The oracles judge reference products: correct ones score 100 %, broken ones less."""

import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

from bench.oracle import judge, npm_command, prepare, product_suite

SLUGIFY = '''
import re
import unicodedata


def slugify(text, max_length=None):
    slug = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    if max_length is not None and len(slug) > max_length:
        kept = ""
        for word in slug.split("-"):
            candidate = f"{kept}-{word}" if kept else word
            if len(candidate) > max_length:
                break
            kept = candidate
        slug = kept or slug[:max_length]
    return slug
'''

TODO = '''
import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="todo_cli", description="Gestion de taches")
    parser.add_argument("--db", default="todo.json")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("add").add_argument("title")
    sub.add_parser("list")
    sub.add_parser("done").add_argument("id", type=int)
    sub.add_parser("remove").add_argument("id", type=int)
    args = parser.parse_args(argv)
    db = Path(args.db)
    data = json.loads(db.read_text(encoding="utf-8")) if db.exists() else {"next_id": 1, "tasks": []}
    if args.cmd == "list":
        for task in sorted(data["tasks"], key=lambda t: t["id"]):
            print(f"{task['id']} [{'x' if task['done'] else ' '}] {task['title']}")
        return 0
    if args.cmd == "add":
        title = args.title.strip()
        if not title:
            print("titre vide", file=sys.stderr)
            return 2
        data["tasks"].append({"id": data["next_id"], "title": title, "done": False})
        print(data["next_id"])
        data["next_id"] += 1
    else:
        task = next((t for t in data["tasks"] if t["id"] == args.id), None)
        if task is None:
            print("id inconnu", file=sys.stderr)
            return 1
        if args.cmd == "done":
            task["done"] = True
        else:
            data["tasks"].remove(task)
    db.write_text(json.dumps(data), encoding="utf-8")
    return 0
'''

NOTES = '''
import os
import sqlite3
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = ""


def create_app():
    path = os.environ.get("NOTES_DB", "notes.db")
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                   "title TEXT, body TEXT, created_at TEXT)")
    app = FastAPI()

    def rows(sql, params=()):
        with sqlite3.connect(path) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute(sql, params)]

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/notes", status_code=201)
    def create(note: NoteIn):
        with sqlite3.connect(path) as db:
            cur = db.execute("INSERT INTO notes (title, body, created_at) VALUES (?, ?, ?)",
                             (note.title, note.body, datetime.now(timezone.utc).isoformat()))
        return rows("SELECT * FROM notes WHERE id = ?", (cur.lastrowid,))[0]

    @app.get("/notes")
    def listing(q: str | None = None):
        notes = rows("SELECT * FROM notes ORDER BY id")
        if q:
            notes = [n for n in notes if q.lower() in (n["title"] + " " + n["body"]).lower()]
        return notes

    @app.get("/notes/{nid}")
    def get(nid: int):
        found = rows("SELECT * FROM notes WHERE id = ?", (nid,))
        if not found:
            raise HTTPException(404)
        return found[0]

    @app.put("/notes/{nid}")
    def put(nid: int, note: NoteIn):
        get(nid)
        with sqlite3.connect(path) as db:
            db.execute("UPDATE notes SET title = ?, body = ? WHERE id = ?", (note.title, note.body, nid))
        return get(nid)

    @app.delete("/notes/{nid}", status_code=204)
    def delete(nid: int):
        get(nid)
        with sqlite3.connect(path) as db:
            db.execute("DELETE FROM notes WHERE id = ?", (nid,))
        return Response(status_code=204)

    return app
'''

NOTES_MAIN = '''
import os

import uvicorn

from notes_api.app import create_app

uvicorn.run(create_app(), host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
'''


def _product(root: Path, package: str, files: dict[str, str], deps: list[str]) -> Path:
    root.mkdir(parents=True)
    dep_list = ", ".join(f'"{d}"' for d in deps)
    (root / "pyproject.toml").write_text(textwrap.dedent(f"""
        [project]
        name = "{package.replace('_', '-')}"
        version = "0.1.0"
        requires-python = ">=3.12"
        dependencies = [{dep_list}]

        [dependency-groups]
        dev = ["pytest>=8"]

        [tool.pytest.ini_options]
        pythonpath = ["."]
        """), encoding="utf-8")
    (root / ".python-version").write_text("3.12\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    subprocess.run(["uv", "lock", "-q"], cwd=root, check=True, timeout=300)
    return root


def test_b1_reference_scores_full_and_broken_scores_less(tmp_path):
    good = _product(tmp_path / "good", "slugify_lib", {"slugify_lib/__init__.py": SLUGIFY}, [])
    broken = _product(tmp_path / "broken", "slugify_lib",
                      {"slugify_lib/__init__.py": "def slugify(text, max_length=None):\n    return text.lower()\n"}, [])

    good_report = judge("B1", good, "slugify_lib", "lib")
    broken_report = judge("B1", broken, "slugify_lib", "lib")

    assert good_report["m6_oracle"]["rate"] == 1.0, good_report["m6_oracle"]["checks"]
    assert good_report["m5_suite"]["green"] and good_report["m7_smoke"]["ok"]
    assert broken_report["m6_oracle"]["rate"] < 0.5


def test_b2_reference_scores_full_and_broken_scores_less(tmp_path):
    main = "import sys\nfrom todo_cli.cli import main\nsys.exit(main())\n"
    good = _product(tmp_path / "good", "todo_cli",
                    {"todo_cli/__init__.py": "", "todo_cli/cli.py": TODO, "todo_cli/__main__.py": main}, [])
    broken = _product(tmp_path / "broken", "todo_cli",
                      {"todo_cli/__init__.py": "", "todo_cli/cli.py": TODO.replace("[{'x'", "({'x'"),
                       "todo_cli/__main__.py": main}, [])

    good_report = judge("B2", good, "todo_cli", "cli")
    broken_report = judge("B2", broken, "todo_cli", "cli")

    assert good_report["m6_oracle"]["rate"] == 1.0, good_report["m6_oracle"]["checks"]
    assert good_report["m7_smoke"]["ok"]
    assert broken_report["m6_oracle"]["rate"] < 1.0


def test_b3_reference_scores_full(tmp_path):
    good = _product(tmp_path / "good", "notes_api",
                    {"notes_api/__init__.py": "", "notes_api/app.py": NOTES, "notes_api/__main__.py": NOTES_MAIN},
                    ["fastapi>=0.110", "uvicorn>=0.29"])

    report = judge("B3", good, "notes_api", "api")

    assert report["m6_oracle"]["rate"] == 1.0, report["m6_oracle"]["checks"]
    assert report["m7_smoke"]["ok"], report["m7_smoke"]


def test_a_product_without_lock_or_env_scores_zero(tmp_path):
    root = tmp_path / "nothing"
    root.mkdir()
    (root / "pyproject.toml").write_text("not toml at all [", encoding="utf-8")

    report = judge("B1", root, "slugify_lib", "lib")

    assert not report["env_built"]
    assert report["m6_oracle"]["total"] == 0 and not report["m7_smoke"]["ok"]


# B4: a fullstack reference product (FastAPI serving frontend/dist + a tiny Vite React TS app).

COUNTER = '''
import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app():
    path = os.environ.get("COUNTER_DB", "counter.db")
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS counter (id INTEGER PRIMARY KEY CHECK (id = 1), value INTEGER)")
        db.execute("INSERT OR IGNORE INTO counter VALUES (1, 0)")
    app = FastAPI()

    def value():
        with sqlite3.connect(path) as db:
            return db.execute("SELECT value FROM counter WHERE id = 1").fetchone()[0]

    def write(sql):
        with sqlite3.connect(path) as db:
            db.execute(sql)
        return {"value": value()}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/counter")
    def get():
        return {"value": value()}

    @app.post("/api/counter/increment")
    def increment():
        return write("UPDATE counter SET value = value + 1 WHERE id = 1")

    @app.post("/api/counter/reset")
    def reset():
        return write("UPDATE counter SET value = 0 WHERE id = 1")

    if DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(DIST / "index.html")

    return app
'''

# Broken: the value lives in memory (lost on restart) and the built frontend is not served.
COUNTER_BROKEN = '''
from fastapi import FastAPI


def create_app():
    app = FastAPI()
    state = {"value": 0}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/counter")
    def get():
        return dict(state)

    @app.post("/api/counter/increment")
    def increment():
        state["value"] += 1
        return dict(state)

    @app.post("/api/counter/reset")
    def reset():
        state["value"] = 0
        return dict(state)

    return app
'''

COUNTER_MAIN = NOTES_MAIN.replace("notes_api", "counter_app")

FRONTEND = {
    "frontend/package.json": """{
  "name": "counter-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {"build": "vite build", "test": "vitest run"},
  "dependencies": {"react": "^19.0.0", "react-dom": "^19.0.0"},
  "devDependencies": {"@vitejs/plugin-react": "^6.0.0", "vite": "^8.0.0", "vitest": "^5.0.0"}
}
""",
    "frontend/index.html": """<!doctype html>
<html lang="fr"><head><meta charset="UTF-8" /><title>Compteur</title></head>
<body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>
""",
    "frontend/vite.config.ts": """import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({ plugins: [react()], server: { proxy: { "/api": "http://127.0.0.1:8000" } } });
""",
    "frontend/src/main.tsx": """import { createRoot } from "react-dom/client";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(<App />);
""",
    "frontend/src/App.tsx": """import { useEffect, useState } from "react";

export function App() {
  const [value, setValue] = useState(0);
  useEffect(() => { fetch("/api/counter").then((r) => r.json()).then((d) => setValue(d.value)); }, []);
  const call = (path: string) => fetch(path, { method: "POST" }).then((r) => r.json()).then((d) => setValue(d.value));
  return (
    <main>
      <h1>Compteur</h1>
      <p>{value}</p>
      <button onClick={() => call("/api/counter/increment")}>+1</button>
      <button onClick={() => call("/api/counter/reset")}>Remise à zéro</button>
    </main>
  );
}
""",
    "frontend/src/counter.ts": "export function next(value: number): number {\n  return value + 1;\n}\n",
    "frontend/src/counter.test.ts": """import { expect, test } from "vitest";
import { next } from "./counter";

test("next adds one", () => {
  expect(next(1)).toBe(2);
});
""",
}


@pytest.fixture(scope="module")
def b4_reports(tmp_path_factory):
    """Judge the B4 reference product and its broken variant once (npm + uv: about a minute)."""
    root = tmp_path_factory.mktemp("b4")
    good = _product(root / "good", "counter_app",
                    {"counter_app/__init__.py": "", "counter_app/app.py": COUNTER,
                     "counter_app/__main__.py": COUNTER_MAIN, **FRONTEND},
                    ["fastapi>=0.110", "uvicorn>=0.29"])
    subprocess.run([npm_command(), "install", "--no-audit", "--no-fund"], cwd=good / "frontend",
                   check=True, timeout=600, capture_output=True)
    assert (good / "frontend" / "package-lock.json").is_file()
    broken = root / "broken"
    shutil.copytree(good, broken, ignore=shutil.ignore_patterns("node_modules", ".venv"))
    (broken / "counter_app" / "app.py").write_text(COUNTER_BROKEN, encoding="utf-8")
    test_file = broken / "frontend" / "src" / "counter.test.ts"
    test_file.write_text(test_file.read_text(encoding="utf-8").replace("toBe(2)", "toBe(3)"), encoding="utf-8")
    return judge("B4", good, "counter_app", "fullstack"), judge("B4", broken, "counter_app", "fullstack")


def test_b4_reference_scores_full_with_frontend_built_and_tested(b4_reports):
    good, _ = b4_reports

    assert good["frontend_built"], good["frontend_detail"]
    assert good["m6_oracle"]["rate"] == 1.0, good["m6_oracle"]["checks"]
    assert good["m6_oracle"]["total"] == 8
    assert good["m7_smoke"]["ok"], good["m7_smoke"]
    suite = good["m5_suite"]
    assert suite["green"] and suite["frontend"]["passed"] == 1 and suite["passed"] == 2, suite


def test_b4_broken_variant_scores_less_and_its_failing_frontend_test_is_counted(b4_reports):
    _, broken = b4_reports

    failed = {c["id"] for c in broken["m6_oracle"]["checks"] if not c["passed"]}
    assert failed == {"index_serves_built_page", "built_asset_served", "persists_across_restart"}, failed
    assert not broken["m7_smoke"]["ok"]
    suite = broken["m5_suite"]
    assert not suite["green"] and suite["frontend"]["failed"] == 1 and suite["failed"] == 1, suite


def test_a_frontend_that_cannot_install_is_reported_and_never_green(tmp_path):
    root = _product(tmp_path / "nofront", "counter_app", {"counter_app/__init__.py": ""}, [])
    (root / "frontend").mkdir()
    (root / "frontend" / "package.json").write_text('{"name": "x", "version": "0.0.0"}', encoding="utf-8")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:
        product = prepare(root, "counter_app", Path(work))
        suite = product_suite(product)

    assert product.frontend and not product.frontend_ok
    assert "npm ci" in product.frontend_detail
    assert not suite["green"] and suite["frontend"]["failed"] == 1
