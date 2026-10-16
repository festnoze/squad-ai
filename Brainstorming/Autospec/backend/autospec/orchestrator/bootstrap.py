"""Deterministic greenfield scaffolds and a bounded, real connectivity preflight.

The bootstrap owns only absent files or exact pristine workspace templates.
Once prepared, files belong to the project: subsequent calls never regenerate
them. No agent is needed to install boilerplate or wire the first HTTP route.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

from ..config import BACKEND_DIR, PROJECT_DIR, settings
from . import workspace

VERSION = 1
MANIFEST = ".autospec-bootstrap.json"
LEGACY_MANIFEST = ".autospec/bootstrap.json"
# Versions already exercised by Autospec's own frontend lockfile. Transitive
# dependencies are resolved once, then every install uses npm ci.
FRONTEND_VERSIONS = {
    "react": "18.3.1", "react-dom": "18.3.1", "@testing-library/jest-dom": "6.9.1",
    "@testing-library/react": "16.3.2", "@types/react": "18.3.31", "@types/react-dom": "18.3.7",
    "@vitejs/plugin-react": "4.7.0", "jsdom": "25.0.1", "typescript": "5.9.3",
    "vite": "6.4.4", "vitest": "4.1.11", "@vitest/coverage-v8": "4.1.11",
}
SAFE_ENV_KEYS = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
    "NUMBER_OF_PROCESSORS", "OS", "PROCESSOR_ARCHITECTURE", "LANG", "LC_ALL", "USER",
    # Toolchain/cache locations are configuration, never provider credentials.
    "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "NPM_CONFIG_CACHE", "CARGO_HOME",
    "RUSTUP_HOME", "GOCACHE", "GOMODCACHE", "GOPATH", "GOROOT",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
}


@dataclass(frozen=True)
class BootstrapResult:
    ok: bool
    detail: str
    skipped: bool = False
    infra: bool = False
    fingerprint: str = ""
    files: tuple[str, ...] = ()


class BootstrapFailure(Exception):
    def __init__(self, detail: str, *, infra: bool = False, exit_code: int | None = None):
        super().__init__(detail)
        self.infra = infra
        self.exit_code = exit_code


PYTHON_APP = '''"""Application factory; feature modules expose register(app)."""
import inspect
import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from __PACKAGE__.features import discover

USE_DATABASE = __USE_DATABASE__


def health() -> dict:
    result = {"status": "ok", "service": "autospec-bootstrap", "database": "none"}
    if os.environ.get("AUTOSPEC_BOOTSTRAP_TOKEN"):
        result["probe"] = os.environ["AUTOSPEC_BOOTSTRAP_TOKEN"]
    if USE_DATABASE:
        url = os.environ.get("DATABASE_URL", "sqlite:///data/app.db")
        if not url.startswith("sqlite:///"):
            raise ValueError("This scaffold requires a sqlite:/// DATABASE_URL")
        filename = url.removeprefix("sqlite:///")
        if filename != ":memory:":
            Path(filename).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(filename, timeout=5) as connection:
            if connection.execute("SELECT 1").fetchone() != (1,):
                raise RuntimeError("Database probe failed")
        result["database"] = "ok"
    return result


def create_app() -> FastAPI:
    app = FastAPI(title=__TITLE__)
    app.get("/health")(health)
    app.get("/api/health")(health)
    for register in discover():
        params = inspect.signature(register).parameters.values()
        positional = any(p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD,
                                    p.VAR_POSITIONAL) for p in params)
        register(app) if positional else register()
    static = Path(os.environ.get("AUTOSPEC_STATIC_DIR", "frontend/dist"))
    if static.is_dir():
        app.mount("/", StaticFiles(directory=str(static), html=True), name="frontend")
    return app
'''

PYTHON_MAIN = '''"""HTTP entrypoint. Feature routes live in __PACKAGE__/features/*.py."""
import argparse
import os
import uvicorn
from __PACKAGE__.app import create_app

app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generated HTTP application")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
'''

WEB_FEATURES_INIT = '''"""Feature plugin discovery for the HTTP application.

Each module under {package}/features/ exposes register(app). The application
factory passes the FastAPI instance to this hook; register routes with
app.include_router(router) or decorators. Do not recreate app or launch a
server here. Hooks with no arguments remain supported. New features never
need to edit main.py or app.py to be loaded.
"""

import importlib''' + workspace.FEATURES_INIT_TEMPLATE.split("import importlib", 1)[1]

PYTHON_TEST = '''from fastapi.testclient import TestClient
from __PACKAGE__.app import create_app


def test_health_checks_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "probe.db"))
    with TestClient(create_app()) as client:
        for endpoint in ("/health", "/api/health"):
            response = client.get(endpoint)
            assert response.status_code == 200
            assert response.json() == {
                "status": "ok", "service": "autospec-bootstrap", "database": __DATABASE_STATUS__,
            }
'''

GO_MAIN = '''package main

import (
    "encoding/json"
    "flag"
    "log"
    "net/http"
    "os"
    "time"
)

func health(w http.ResponseWriter, r *http.Request) {
    if r.Method != http.MethodGet { w.WriteHeader(http.StatusMethodNotAllowed); return }
    w.Header().Set("Content-Type", "application/json")
    body := map[string]string{
        "status": "ok", "service": "autospec-bootstrap", "database": "none",
    }
    if token := os.Getenv("AUTOSPEC_BOOTSTRAP_TOKEN"); token != "" { body["probe"] = token }
    _ = json.NewEncoder(w).Encode(body)
}

func newHandler() http.Handler {
    mux := http.NewServeMux()
    mux.HandleFunc("/health", health)
    mux.HandleFunc("/api/health", health)
    static := os.Getenv("AUTOSPEC_STATIC_DIR")
    if static == "" { static = "frontend/dist" }
    if info, err := os.Stat(static); err == nil && info.IsDir() {
        mux.Handle("/", http.FileServer(http.Dir(static)))
    }
    return mux
}

func main() {
    flag.Parse()
    host, port := os.Getenv("HOST"), os.Getenv("PORT")
    if host == "" { host = "0.0.0.0" }
    if port == "" { port = "8000" }
    server := &http.Server{Addr: host + ":" + port, Handler: newHandler(),
        ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second,
        WriteTimeout: 10 * time.Second, IdleTimeout: 60 * time.Second}
    log.Fatal(server.ListenAndServe())
}
'''

GO_TEST = '''package main
import ("encoding/json"; "net/http/httptest"; "testing")
func TestBootstrapHealth(t *testing.T) {
    for _, path := range []string{"/health", "/api/health"} {
        response := httptest.NewRecorder()
        newHandler().ServeHTTP(response, httptest.NewRequest("GET", path, nil))
        var body map[string]string
        if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil { t.Fatal(err) }
        if response.Code != 200 || body["status"] != "ok" || body["database"] != "none" {
            t.Fatalf("unexpected health: %d %v", response.Code, body)
        }
    }
}
'''

RUST_MAIN = '''use axum::{routing::get, Json, Router};
use serde_json::{json, Value};
use tower_http::services::ServeDir;

async fn health() -> Json<Value> {
    let mut body = json!({"status": "ok", "service": "autospec-bootstrap", "database": "none"});
    if let Ok(token) = std::env::var("AUTOSPEC_BOOTSTRAP_TOKEN") { body["probe"] = json!(token); }
    Json(body)
}

#[tokio::main]
async fn main() {
    if std::env::args().any(|a| a == "--help" || a == "-h") {
        println!("HTTP application: configure HOST and PORT (default 0.0.0.0:8000)");
        return;
    }
    let host = std::env::var("HOST").unwrap_or_else(|_| "0.0.0.0".into());
    let port = std::env::var("PORT").unwrap_or_else(|_| "8000".into());
    let static_dir = std::env::var("AUTOSPEC_STATIC_DIR")
        .unwrap_or_else(|_| "frontend/dist".into());
    let app = Router::new().route("/health", get(health)).route("/api/health", get(health))
        .fallback_service(ServeDir::new(static_dir).append_index_html_on_directories(true));
    let listener = tokio::net::TcpListener::bind(format!("{host}:{port}")).await
        .expect("HTTP bind failed");
    axum::serve(listener, app).await.expect("HTTP server failed");
}

#[cfg(test)]
mod tests {
    #[tokio::test]
    async fn bootstrap_health() {
        let body = super::health().await.0;
        assert_eq!(body["status"], "ok");
        assert_eq!(body["database"], "none");
    }
}
'''

NODE_MAIN = '''import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

export function createServer() {
  const root = path.resolve(process.env.AUTOSPEC_STATIC_DIR || "frontend/dist");
  return http.createServer(async (request, response) => {
    try {
      const pathname = new URL(request.url || "/", "http://localhost").pathname;
      if (["/health", "/api/health"].includes(pathname)) {
        response.writeHead(200, { "Content-Type": "application/json" });
        response.end(JSON.stringify({ status: "ok", service: "autospec-bootstrap", database: "none",
          ...(process.env.AUTOSPEC_BOOTSTRAP_TOKEN ? { probe: process.env.AUTOSPEC_BOOTSTRAP_TOKEN } : {}) }));
        return;
      }
      const file = path.resolve(root, "." + decodeURIComponent(pathname));
      if (file !== root && !file.startsWith(root + path.sep)) {
        response.writeHead(403); response.end(); return;
      }
      const target = (await stat(file)).isDirectory() ? path.join(file, "index.html") : file;
      const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml" };
      response.writeHead(200, { "Content-Type": types[path.extname(target)] || "application/octet-stream" });
      response.end(await readFile(target));
    } catch { response.writeHead(404); response.end("Not found"); }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  if (process.argv.includes("--help")) console.log("HTTP application: HOST=0.0.0.0 PORT=8000");
  else createServer().listen(Number(process.env.PORT || 8000), process.env.HOST || "0.0.0.0");
}
'''

NODE_TEST = '''import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "./main.js";
test("bootstrap health responds over HTTP", async () => {
  const server = createServer();
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  try {
    const response = await fetch(`http://127.0.0.1:${server.address().port}/api/health`);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { status: "ok", service: "autospec-bootstrap", database: "none" });
  } finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});
'''

FRONTEND_HEALTH = '''import { useEffect, useState } from "react";

export default function BootstrapHealth() {
  const [status, setStatus] = useState("Connexion à l'API…");
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/health", { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(`API HTTP ${response.status}`);
        const body = await response.json();
        if (body.status !== "ok" || body.service !== "autospec-bootstrap") throw new Error("API invalide");
        setStatus(body.database === "ok" ? "Frontend → API → base de données : OK" : "Frontend → API : OK");
      })
      .catch(error => { if (error.name !== "AbortError") setStatus(`Connexion impossible : ${error.message}`); });
    return () => controller.abort();
  }, []);
  return <section><h1>Application prête</h1><p role="status">{status}</p></section>;
}
'''

FRONTEND_TEST = '''import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import BootstrapHealth from "./BootstrapHealth";
afterEach(() => vi.unstubAllGlobals());
it("verifies the relative API connection", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "ok", service: "autospec-bootstrap", database: "ok" }) });
  vi.stubGlobal("fetch", fetchMock);
  render(<BootstrapHealth />);
  expect(await screen.findByText("Frontend → API → base de données : OK")).toBeInTheDocument();
  expect(fetchMock.mock.calls[0][0]).toBe("/api/health");
});
it("surfaces a broken API connection", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Unavailable")));
  render(<BootstrapHealth />);
  expect(await screen.findByText(/Connexion impossible/)).toBeInTheDocument();
});
'''

FRONTEND_APP = workspace.FE_APP_TSX.replace(
    "  if (features.length === 0)",
    '  // The technical probe is only the initial screen, never a product feature.\n'
    '  const productFeatures = features.filter(([path]) => !path.endsWith("/BootstrapHealth.tsx"));\n'
    '  const visibleFeatures = productFeatures.length ? productFeatures : features;\n'
    "  if (visibleFeatures.length === 0)",
).replace("{features.map", "{visibleFeatures.map")


def _stack(state: Any) -> dict[str, str]:
    return dict(getattr(state, "technical_stack", {}) or {})


def _digest(files: dict[str, str], stack: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps([VERSION, stack, files], sort_keys=True).encode()).hexdigest()


def _safe_path(ws: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise ValueError("Chemin bootstrap invalide")
    portable = relative.replace("\\", "/")
    if ":" in portable or ".." in portable.split("/") or PureWindowsPath(relative).drive:
        raise ValueError("Chemin bootstrap hors du projet")
    path = ws / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(ws.resolve()):
        raise ValueError("Chemin bootstrap hors du projet")
    return path


def _existing_manifest(ws: Path) -> Path:
    current = _safe_path(ws, MANIFEST)
    if current.is_file():
        return current
    legacy = _safe_path(ws, LEGACY_MANIFEST)
    return legacy if legacy.is_file() else current


def _read_manifest(ws: Path, stack: dict[str, str]) -> dict[str, Any]:
    """Validate persisted metadata before trusting it for reuse or execution."""
    manifest = json.loads(_existing_manifest(ws).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Le manifeste bootstrap doit être un objet JSON")
    if type(manifest.get("version")) is not int or manifest["version"] != VERSION:
        raise ValueError("Version du manifeste bootstrap absente ou non prise en charge")
    saved_stack = manifest.get("stack")
    if not isinstance(saved_stack, dict) or not saved_stack or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in saved_stack.items()
    ):
        raise ValueError("Stack du manifeste bootstrap invalide")
    if saved_stack != stack:
        raise ValueError("La stack a changé après le bootstrap ; migration explicite nécessaire")
    files = manifest.get("files")
    if not isinstance(files, list) or not all(isinstance(name, str) for name in files):
        raise ValueError("La liste files du manifeste bootstrap est invalide")
    if len(files) != len(set(files)):
        raise ValueError("Le manifeste bootstrap contient des chemins dupliqués")
    for name in files:
        _safe_path(ws, name)
    fingerprint = manifest.get("fingerprint")
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ValueError("Empreinte du manifeste bootstrap absente ou invalide")
    return manifest


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Atomic publication keeps an interrupted save from truncating metadata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_runtime_paths(state: Any, ws: Path) -> None:
    # Installer/build outputs must not follow a workspace junction into another
    # project's environment, binary directory or database. A venv's interpreter
    # itself may legitimately symlink to the system Python; check its directory.
    stack = _stack(state)
    backend = "none" if stack.get("kind") == "frontend" else stack.get("backend", "python")
    targets = {
        "python": [".venv"], "go": [".autospec", ".autospec/bootstrap.exe", ".autospec/bootstrap"],
        "rust": ["target"], "node": ["node_modules"],
    }.get(backend, [])
    if stack.get("database") == "sqlite":
        targets.extend([".autospec", ".autospec/bootstrap.db"])
    for name in targets:
        _safe_path(ws, name)
    if stack.get("frontend") == "react":
        frontend = _frontend_rel(state, ws)
        for name in (frontend, frontend + "/node_modules", frontend + "/dist"):
            _safe_path(ws, name)


def _frontend_rel(state: Any, ws: Path) -> str:
    streams = workspace.frontend_streams(state)
    rel = (streams[0].file_root or "frontend") if streams else "frontend"
    target = (ws / rel).resolve()
    if not target.is_relative_to(ws.resolve()) or target == ws.resolve():
        raise ValueError("Le frontend doit être dans un sous-dossier du projet")
    return target.relative_to(ws.resolve()).as_posix()


def _templates(state: Any, ws: Path, stack: dict[str, str]) -> dict[str, str]:
    kind = stack.get("kind", "api")
    backend = "none" if kind == "frontend" else stack.get("backend", "python")
    pkg = workspace.package_name(state)
    db = stack.get("database", "none")
    if db not in ("sqlite", "none"):
        raise ValueError(f"Préflight déterministe indisponible pour la base {db}")
    if db == "sqlite" and backend != "python":
        raise ValueError(f"Le template {backend} ne prend pas encore SQLite en charge")
    if stack.get("frontend", "none") not in ("none", "react"):
        raise ValueError("Le template frontend déterministe disponible est React")
    expected_framework = {"python": "fastapi", "go": "net/http", "rust": "axum", "node": "node:http", "none": ""}.get(backend)
    if backend != "none" and stack.get("framework", "") not in ("", expected_framework):
        raise ValueError(f"Le template {backend} utilise {expected_framework}, pas {stack['framework']}")
    files: dict[str, str] = {}
    if kind not in ("cli", "library", "library-fast"):
        if backend == "python":
            if stack.get("framework", "fastapi") not in ("", "fastapi"):
                raise ValueError("Le template Python HTTP disponible est FastAPI")
            existing = _safe_path(ws, "pyproject.toml")
            ui_dep = '\n    "pytest-playwright>=0.5",' if (
                existing.exists() and "pytest-playwright" in existing.read_text(encoding="utf-8")
            ) else ""
            pyproject = workspace.PYPROJECT_TEMPLATE.format(package=pkg, name="__TITLE__", ui_dep=ui_dep)
            pyproject = pyproject.replace('"Generated by Autospec: __TITLE__"', json.dumps("Generated by Autospec: " + state.name, ensure_ascii=False))
            pyproject = pyproject.replace("dependencies = []", 'dependencies = ["fastapi==0.136.3", "uvicorn==0.49.0"]')
            pyproject = pyproject.replace('"pytest>=8.0"', '"pytest==9.0.3", "httpx==0.28.1"')
            files.update({"pyproject.toml": pyproject, "main.py": PYTHON_MAIN.replace("__PACKAGE__", pkg),
                f"{pkg}/app.py": PYTHON_APP.replace("__PACKAGE__", pkg).replace("__USE_DATABASE__", repr(db == "sqlite")).replace("__TITLE__", repr(state.name)),
                "tests/test_bootstrap.py": PYTHON_TEST.replace("__PACKAGE__", pkg).replace("__DATABASE_STATUS__", repr("ok" if db == "sqlite" else "none")),
                f"{pkg}/__init__.py": "", f"{pkg}/features/__init__.py": WEB_FEATURES_INIT.format(package=pkg),
                ".gitignore": workspace.GITIGNORE_TEMPLATE + ".env\n.env.*\n"})
        elif backend == "go":
            files.update({"go.mod": workspace.GO_MOD_TEMPLATE.format(package=pkg), "main.go": GO_MAIN, "bootstrap_test.go": GO_TEST})
        elif backend == "rust":
            cargo = workspace.CARGO_TOML_TEMPLATE.format(package=pkg) + '\naxum = "=0.8.4"\ntokio = { version = "1", features = ["full"] }\nserde_json = "1"\ntower-http = { version = "0.6", features = ["fs"] }\n'
            files.update({"Cargo.toml": cargo, "src/main.rs": RUST_MAIN})
        elif backend == "node":
            files.update({"package.json": json.dumps({"name": pkg.replace("_", "-"), "private": True, "version": "0.1.0", "type": "module", "scripts": {"start": "node main.js", "test": "node --test"}}, indent=2) + "\n", "main.js": NODE_MAIN, "bootstrap.test.js": NODE_TEST})
        elif backend != "none":
            raise ValueError(f"Backend non supporté par le bootstrap : {backend}")
    if stack.get("frontend") == "react":
        rel = _frontend_rel(state, ws)
        package = json.loads(workspace.FE_PACKAGE_JSON_TEMPLATE.format(package=pkg))
        for section in ("dependencies", "devDependencies"):
            package[section] = {key: FRONTEND_VERSIONS[key] for key in package[section]}
        fe = {"package.json": json.dumps(package, indent=2) + "\n", "tsconfig.json": workspace.FE_TSCONFIG_TEMPLATE,
            "vite.config.ts": workspace.FE_VITE_CONFIG_TEMPLATE, "index.html": workspace.FE_INDEX_HTML_TEMPLATE.format(name=html.escape(state.name)),
            "src/main.tsx": workspace.FE_MAIN_TSX, "src/App.tsx": FRONTEND_APP,
            "src/App.test.tsx": workspace.FE_APP_TEST_TSX, "src/setupTests.ts": workspace.FE_SETUP_TESTS,
            ".gitignore": workspace.FE_GITIGNORE}
        if backend != "none":
            fe.update({"src/features/BootstrapHealth.tsx": FRONTEND_HEALTH, "src/features/BootstrapHealth.test.tsx": FRONTEND_TEST})
        files.update({f"{rel}/{name}": content for name, content in fe.items()})
    return files


def _pristine(state: Any, ws: Path) -> dict[str, set[str]]:
    pkg = workspace.package_name(state)
    result = {"main.py": {workspace.MAIN_TEMPLATE.format(package=pkg)},
        f"{pkg}/features/__init__.py": {workspace.FEATURES_INIT_TEMPLATE.format(package=pkg)},
        "main.js": {workspace.NODE_MAIN_TEMPLATE},
        "package.json": {workspace.NODE_PACKAGE_TEMPLATE.format(package=pkg.replace("_", "-"))},
        "main.go": {workspace.GO_MAIN_TEMPLATE, workspace.GO_MAIN_TEMPLATE.format(package=pkg)},
        "src/main.rs": {workspace.RUST_MAIN_TEMPLATE, workspace.RUST_MAIN_TEMPLATE.format(package=pkg)},
        "Cargo.toml": {workspace.CARGO_TOML_TEMPLATE.format(package=pkg)},
        ".gitignore": {workspace.GITIGNORE_TEMPLATE},
        "pyproject.toml": {workspace.PYPROJECT_TEMPLATE.format(package=pkg, name=state.name, ui_dep=ui) for ui in ("", '\n    "pytest-playwright>=0.5",')}}
    if _stack(state).get("frontend") == "react":
        rel = _frontend_rel(state, ws)
        result[f"{rel}/package.json"] = {workspace.FE_PACKAGE_JSON_TEMPLATE.format(package=pkg)}
        result[f"{rel}/src/App.tsx"] = {workspace.FE_APP_TSX}
        result[f"{rel}/index.html"] = {workspace.FE_INDEX_HTML_TEMPLATE.format(name=state.name)}
    return result


def prepare(state: Any, ws: Path) -> BootstrapResult:
    """Prepare only a selected greenfield stack; never overwrite developed code."""
    if getattr(state, "brownfield_path", "") or getattr(state, "product_profile", "") == "brownfield":
        return BootstrapResult(True, "Projet existant : aucun scaffold remplacé", skipped=True)
    stack = _stack(state)
    if not stack:
        return BootstrapResult(True, "Aucune stack technique sélectionnée", skipped=True)
    try:
        _validate_runtime_paths(state, ws)
        manifest_path = _safe_path(ws, MANIFEST)
        existing_manifest = _existing_manifest(ws)
        if existing_manifest.exists():
            manifest = _read_manifest(ws, stack)
            files = manifest["files"]
            missing = [name for name in files if not _safe_path(ws, name).is_file()]
            if missing:
                return BootstrapResult(False, "Fichiers bootstrap absents : " + ", ".join(missing))
            if existing_manifest != manifest_path:
                # Stable project metadata must travel into Git worktrees; only
                # volatile logs, binaries and probe databases belong in .autospec/.
                _write_manifest(manifest_path, manifest)
            return BootstrapResult(True, "Bootstrap existant conservé", fingerprint=manifest.get("fingerprint", ""), files=tuple(files))
        files = _templates(state, ws, stack)
        pristine = _pristine(state, ws)
        conflicts = []
        for name, content in files.items():
            target = _safe_path(ws, name)
            if target.exists():
                existing = target.read_text(encoding="utf-8")
                if existing != content and existing not in pristine.get(name, set()):
                    conflicts.append(name)
        if conflicts:
            return BootstrapResult(False, "Bootstrap interrompu pour préserver les fichiers modifiés : " + ", ".join(conflicts))
        for name, content in files.items():
            path = _safe_path(ws, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                path.write_text(content, encoding="utf-8")
        fingerprint = _digest(files, stack)
        _write_manifest(manifest_path, {"version": VERSION, "stack": stack, "files": sorted(files), "fingerprint": fingerprint})
        return BootstrapResult(True, "Socle technique déterministe créé", fingerprint=fingerprint, files=tuple(sorted(files)))
    except (OSError, ValueError, TypeError) as exc:
        return BootstrapResult(False, f"Bootstrap : {exc}")


def verify_plan_foundation(state: Any, ws: Path, expected_fingerprint: str) -> BootstrapResult:
    """Revalidate the persisted deterministic socle before PLAN admission.

    The state flag is only a cached result: this check binds the physical
    manifest back to that state, verifies the factory-owned path set, and
    confirms every declared artifact is still a regular in-workspace file.
    Product edits to those files are deliberately allowed; v1 manifests do not
    retain per-file content hashes, and the fingerprint identifies the initial
    scaffold rather than asserting that those files remain byte-identical.
    """
    if getattr(state, "brownfield_path", "") or getattr(state, "product_profile", "") == "brownfield":
        return BootstrapResult(True, "Projet existant : aucun socle déterministe à revalider", skipped=True)
    stack = _stack(state)
    if not stack:
        return BootstrapResult(False, "Socle PLAN absent : stack déterministe manquante")
    try:
        _validate_runtime_paths(state, ws)
        manifest_path = _existing_manifest(ws)
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError("Le manifeste bootstrap doit être un fichier régulier")
        manifest_stat = manifest_path.stat()
        if manifest_stat.st_size > 1_048_576 or manifest_stat.st_nlink != 1:
            raise ValueError("Le manifeste bootstrap dépasse la limite ou possède un alias physique")
        manifest = _read_manifest(ws, stack)
        if (not isinstance(expected_fingerprint, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected_fingerprint)
                or manifest["fingerprint"] != expected_fingerprint):
            raise ValueError("Empreinte du socle différente de l'état PLAN")
        expected_files = sorted(_templates(state, ws, stack))
        if manifest["files"] != expected_files:
            raise ValueError("Les chemins du manifeste bootstrap diffèrent du socle attendu")
        for name in manifest["files"]:
            path = _safe_path(ws, name)
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Fichier bootstrap absent ou non régulier : {name}")
            if path.stat().st_nlink != 1:
                raise ValueError(f"Fichier bootstrap lié à un alias physique : {name}")
        return BootstrapResult(True, "Manifeste et fichiers du socle revalidés",
                               fingerprint=manifest["fingerprint"], files=tuple(manifest["files"]))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return BootstrapResult(False, f"Socle PLAN absent ou incohérent : {exc}", infra=True)


def _argv(argv: list[str]) -> list[str]:
    """Resolve npm's JS entrypoint on Windows instead of shell-interpreting args."""
    executable = shutil.which(argv[0])
    if not executable:
        raise BootstrapFailure(f"Outil requis introuvable : {argv[0]}", infra=True)
    if os.name == "nt" and Path(executable).suffix.lower() in (".cmd", ".bat", ".ps1"):
        npm_cli = Path(executable).parent / "node_modules/npm/bin/npm-cli.js"
        node = shutil.which(settings.node_cmd)
        if Path(executable).stem.lower() == "npm" and npm_cli.exists() and node:
            return [node, str(npm_cli), *argv[1:]]
        raise BootstrapFailure(f"Lanceur non exécutable sans shell : {executable}", infra=True)
    return [executable, *argv[1:]]


async def _await_cleanup(task: asyncio.Task):
    """Defer even repeated cancellation until owned resources are released."""
    interrupted = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            interrupted = True
    result = task.result()
    if interrupted:
        raise asyncio.CancelledError
    return result


async def _stop_impl(process) -> None:
    from ..agents.runner import close_owned_process
    await asyncio.to_thread(close_owned_process, process)


async def _stop(process) -> None:
    await _await_cleanup(asyncio.create_task(_stop_impl(process)))


async def _spawn(argv: list[str], cwd: Path, env: dict[str, str]):
    # Retained solely to reject legacy integrations instead of silently falling
    # back to host execution. RuntimeSession is the only product runtime API.
    raise BootstrapFailure("ISOLATION_UNAVAILABLE: host product spawning is disabled", infra=True)


async def _command(argv: list[str], cwd: Path, env: dict[str, str], deadline: float, cancel: asyncio.Event | None) -> str:
    _check_budget(deadline, cancel)
    raise BootstrapFailure("ISOLATION_UNAVAILABLE: host product commands are disabled", infra=True)


def _check_budget(deadline: float, cancel: asyncio.Event | None) -> None:
    if cancel and cancel.is_set():
        raise asyncio.CancelledError
    if time.monotonic() >= deadline:
        raise BootstrapFailure("Préflight interrompu : délai maximal dépassé", infra=True)


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _get(port: int, path: str) -> tuple[int, bytes]:
    reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), timeout=1)
    try:
        writer.write(f"GET {path} HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode())
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(128 * 1024), timeout=2)
        # Servers may split header/body across packets; read through EOF with a cap.
        while len(raw) < 128 * 1024:
            chunk = await asyncio.wait_for(reader.read(128 * 1024 - len(raw)), timeout=2)
            if not chunk:
                break
            raw += chunk
        header, body = raw.split(b"\r\n\r\n", 1)
        if any(line.lower().strip() == b"transfer-encoding: chunked" for line in header.split(b"\r\n")):
            decoded = bytearray()
            while body:
                size_line, body = body.split(b"\r\n", 1)
                size = int(size_line.split(b";", 1)[0], 16)
                if size == 0:
                    break
                if len(body) < size + 2 or body[size:size + 2] != b"\r\n":
                    raise ValueError("Réponse HTTP chunked incomplète")
                decoded.extend(body[:size])
                body = body[size + 2:]
            body = bytes(decoded)
        return int(header.split(b" ", 2)[1]), body
    finally:
        writer.close()
        await writer.wait_closed()


async def _wait_health(port: int, database: str, process: asyncio.subprocess.Process, deadline: float, cancel: asyncio.Event | None, token: str = "") -> None:
    last = "aucune réponse"
    while True:
        _check_budget(deadline, cancel)
        if process.returncode is not None:
            raise BootstrapFailure(f"Le serveur s'est arrêté ({process.returncode}) avant le contrôle HTTP")
        try:
            status, body = await _get(port, "/api/health")
            expected = {"status": "ok", "service": "autospec-bootstrap", "database": "ok" if database == "sqlite" else "none"}
            if token:
                expected["probe"] = token
            if status == 200 and json.loads(body) == expected:
                return
            last = f"HTTP {status} : {body[:500]!r}"
        except (OSError, ValueError, asyncio.TimeoutError) as exc:
            last = str(exc)
        if deadline - time.monotonic() < 0.25:
            raise BootstrapFailure(f"Connexion HTTP invalide : {last}")
        await asyncio.sleep(0.1)


async def verify(state: Any, ws: Path, *, timeout_s: float = 180, cancel: asyncio.Event | None = None) -> BootstrapResult:
    """Install from lockfiles, test/build, then verify HTTP/FE proxy/DB together.

    A single deadline bounds installation and runtime; cancellation always kills
    the owned process trees. Infrastructure failures stop before business agents.
    """
    return await _verify(state, ws, timeout_s=timeout_s, cancel=cancel, runtime_only=False)


async def verify_runtime(state: Any, ws: Path, *, timeout_s: float = 120, cancel: asyncio.Event | None = None,
                         repair_dependencies: bool = False) -> BootstrapResult:
    """Execute existing sources using clean locked Linux dependency images.

    No scaffold, native venv, source rewrite or unlocked resolution occurs.
    Missing local image caches can be rebuilt from existing locks. The initial
    demonstration screen is never required from an evolved business product.
    """
    return await _verify(state, ws, timeout_s=timeout_s, cancel=cancel, runtime_only=True,
                         repair_dependencies=repair_dependencies)


def _runtime_dependencies_missing(state: Any, ws: Path) -> bool:
    """Locks, not a host .venv/node_modules, are the runtime prerequisite.

    Linux image availability/attestation is verified or rebuilt by the confined
    manager. This read-only check never executes product source or tools.
    """
    stack = _stack(state)
    backend = "none" if stack.get("kind") == "frontend" else stack.get("backend", "python")
    lock = "uv.lock" if backend == "python" else "package-lock.json" if backend == "node" else ""
    if lock and not _safe_path(ws, lock).is_file():
        return True
    if stack.get("frontend") == "react":
        return not _safe_path(ws, _frontend_rel(state, ws) + "/package-lock.json").is_file()
    return False


async def _verify(state: Any, ws: Path, *, timeout_s: float, cancel: asyncio.Event | None, runtime_only: bool,
                  repair_dependencies: bool = False) -> BootstrapResult:
    # Preparation remains deterministic and non-executing. Runtime never writes
    # scaffolds back into a delivered product or trusts a product Dockerfile.
    if runtime_only:
        if not _stack(state) or getattr(state, "brownfield_path", "") or getattr(state, "product_profile", "") == "brownfield":
            return BootstrapResult(True, "Aucun bootstrap runtime à vérifier", skipped=True)
        try:
            _validate_runtime_paths(state, ws)
            manifest = _read_manifest(ws, _stack(state))
            missing = [name for name in manifest["files"] if not _safe_path(ws, name).is_file()]
            if missing:
                return BootstrapResult(False, "Fichiers du socle supprimés : " + ", ".join(missing))
            prepared = BootstrapResult(True, "Artefacts existants", fingerprint=manifest["fingerprint"], files=tuple(manifest["files"]))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return BootstrapResult(False, f"Manifeste bootstrap absent ou invalide : {exc}", infra=True)
    else:
        prepared = prepare(state, ws)
    if not prepared.ok or prepared.skipped:
        return prepared
    if cancel and cancel.is_set():
        raise asyncio.CancelledError
    from ..agents.runner import _await_tracked
    try:
        detail = await asyncio.wait_for(
            _await_tracked(lambda: _isolated_preflight(state, ws, timeout_s, runtime_only)),
            timeout=max(.1, timeout_s),
        )
        return BootstrapResult(True, detail, fingerprint=prepared.fingerprint, files=prepared.files)
    except asyncio.TimeoutError:
        return BootstrapResult(False, "Préflight isolé : délai maximal dépassé (ressources possédées nettoyées)", infra=True, fingerprint=prepared.fingerprint)
    except BootstrapFailure as exc:
        return BootstrapResult(False, str(exc), infra=exc.infra, fingerprint=prepared.fingerprint)
    except (OSError, ValueError, RuntimeError) as exc:
        return BootstrapResult(False, f"Préflight isolé : {exc}", infra=True, fingerprint=prepared.fingerprint)


def _isolated_preflight(state: Any, ws: Path, timeout_s: float, runtime_only: bool) -> str:
    import tempfile
    import urllib.request
    from .isolated_validation import IsolatedValidator, RuntimeSession
    from .validation_environment import snapshot_product

    stack = _stack(state)
    backend = "none" if stack.get("kind") == "frontend" else stack.get("backend", "python")
    if backend not in {"python", "node", "none"}:
        raise BootstrapFailure(f"ISOLATION_UNAVAILABLE: toolchain Linux {backend} non provisionnée", infra=True)
    deadline = time.monotonic() + max(.1, timeout_s)
    # Cache/report files are factory-owned, not under the producer root.
    cache = Path(tempfile.gettempdir()) / "autospec-linux-environments"
    validator = IsolatedValidator(cache, docker=settings.docker_cmd, timeout=timeout_s)
    steps = []
    def budget():
        from ..agents.runner import _active_call_cancel
        worker_cancel = _active_call_cancel.get()
        if worker_cancel and worker_cancel.is_set():
            raise asyncio.CancelledError
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BootstrapFailure("Préflight interrompu : délai maximal dépassé", infra=True)
        validator.timeout = validator.manager.timeout = remaining
        return remaining
    if backend != "none":
        budget()
        if not runtime_only:
            validator.manager.ensure_lock(ws, backend)
        environment = validator.manager.prepare(ws, backend, "test")
        if not runtime_only:
            with tempfile.TemporaryDirectory(prefix="autospec-evidence-") as temporary:
                budget()
                if stack.get("kind") in {"cli", "library", "library-fast"}:
                    command = ["/opt/venv/bin/python", "main.py", "--help"] if backend == "python" else ["node", "main.js", "--help"]
                    rc, output, _ = validator.run_command(ws, backend, command)
                    if rc:
                        raise BootstrapFailure(output, exit_code=rc)
                else:
                    suite = validator.run_suite(ws, backend, "test", Path(temporary) / "suite.json", test_args=("tests/test_bootstrap.py",) if backend == "python" else ())
                    if suite.evidence.exit_code or not suite.evidence.report_valid or not suite.evidence.outcomes:
                        raise BootstrapFailure(suite.output, exit_code=suite.evidence.exit_code)
            steps.append(f"{backend}: clean Linux locked dependencies / tests OK ({environment.fingerprint})")
    dist = None
    frontend = ws / _frontend_rel(state, ws) if stack.get("frontend") == "react" else None
    try:
        if frontend:
            budget()
            if not runtime_only:
                validator.manager.ensure_lock(frontend, "node")
            if not runtime_only:
                with tempfile.TemporaryDirectory(prefix="autospec-fe-evidence-") as temporary:
                    suite = validator.run_suite(frontend, "node", "test", Path(temporary) / "suite.json")
                    if suite.evidence.exit_code or not suite.evidence.report_valid or not suite.evidence.outcomes:
                        raise BootstrapFailure(suite.output, exit_code=suite.evidence.exit_code)
            budget()
            rc, output, dist, frontend_env = validator.build_frontend(frontend)
            if rc:
                raise BootstrapFailure(output, exit_code=rc)
            steps.append("React: isolated tests/build OK")
        if stack.get("kind") in {"cli", "library", "library-fast"}:
            return "\n".join(steps)
        with tempfile.TemporaryDirectory(prefix="autospec-live-") as temporary:
            stage = snapshot_product(ws if backend != "none" else frontend, Path(temporary) / "product")
            if dist:
                target = stage / "frontend" / "dist" if backend != "none" else stage / "dist"
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(dist / "dist", target)
            token = uuid.uuid4().hex
            env = {"PORT": "8000", "HOST": "0.0.0.0", "AUTOSPEC_BOOTSTRAP_TOKEN": token}
            if stack.get("database") == "sqlite":
                env["DATABASE_URL"] = "sqlite:////tmp/bootstrap.db"
            if frontend and backend != "none":
                env["AUTOSPEC_STATIC_DIR"] = "/app/frontend/dist"
            if backend == "python":
                command, ecosystem = ["/opt/venv/bin/python", "main.py"], "python"
            elif backend == "node":
                command, ecosystem = ["node", "main.js"], "node"
            else:
                environment, ecosystem = frontend_env, "node"
                # Factory static server; product package scripts never run host.
                static = "const h=require('http'),f=require('fs'),p=require('path');h.createServer((q,r)=>{let n=decodeURIComponent(q.url.split('?')[0]);let a=p.resolve('/app/dist','.'+n);if(!a.startsWith('/app/dist/'))a='/app/dist/index.html';if(!f.existsSync(a)||f.statSync(a).isDirectory())a='/app/dist/index.html';r.setHeader('Content-Type',a.endsWith('.js')?'application/javascript':a.endsWith('.css')?'text/css':'text/html');f.createReadStream(a).pipe(r);}).listen(8000,'0.0.0.0');"
                command = ["node", "-e", static]
            budget()
            with RuntimeSession(stage, environment.image, command, ecosystem=ecosystem, docker=settings.docker_cmd, env=env) as session:
                last = ""
                while True:
                    budget()
                    try:
                        with urllib.request.urlopen(session.origin + ("/api/health" if backend != "none" else "/"), timeout=2) as response:
                            body = response.read(128 * 1024)
                        if backend != "none":
                            expected = {"status": "ok", "service": "autospec-bootstrap", "database": "ok" if stack.get("database") == "sqlite" else "none", "probe": token}
                            if json.loads(body) != expected:
                                raise ValueError(f"unexpected health body: {body[:500]!r}")
                        break
                    except (OSError, ValueError) as exc:
                        last = str(exc)
                        if deadline - time.monotonic() < .3:
                            raise BootstrapFailure(last + "\n" + session.logs())
                        time.sleep(.1)
                steps.append("API → SQLite : SELECT 1 OK" if stack.get("database") == "sqlite" else "isolated HTTP OK")
                if frontend:
                    budget()
                    # Separate browser container: same exact NETNONE network
                    # namespace, no source/DB mount, host launch or client network.
                    steps.append(asyncio.run(_browser_preflight(session,timeout_s=budget(),
                        require_api=backend!="none" and not runtime_only,
                        expected_health=expected if backend!="none" and not runtime_only else None)))
            return "\n".join(steps)
    finally:
        if dist is not None:
            shutil.rmtree(dist)


async def _browser_preflight(session, *, timeout_s: float, require_api: bool, expected_health: dict | None = None) -> str:
    """Actual UI rendering on the exact owned runtime, never host Chromium."""
    from types import SimpleNamespace
    from .isolated_validation import RuntimeSession
    from ..validation.browser_contracts import PlaywrightHarness

    if not isinstance(session,RuntimeSession):
        raise BootstrapFailure("ISOLATION_UNAVAILABLE: actual owned browser runtime required",infra=True)
    if type(timeout_s) not in {int,float} or not 0 < timeout_s <= 3600 or type(require_api) is not bool:
        raise BootstrapFailure("ISOLATION_UNAVAILABLE: bounded browser preflight required",infra=True)
    if require_api and (not isinstance(expected_health,dict) or set(expected_health)!={"status","service","database","probe"}
            or expected_health.get("status")!="ok" or expected_health.get("service")!="autospec-bootstrap"
            or expected_health.get("database") not in {"ok","none"}
            or not isinstance(expected_health.get("probe"),str) or not expected_health["probe"]):
        raise BootstrapFailure("ISOLATION_UNAVAILABLE: supervisor nonce-bound API response required",infra=True)
    parent=session._assert_owned()
    actual=session.inspect_configuration()
    if actual["container_id"]!=parent or actual["network_mode"]!="none" or actual["running"] is not True or actual["published_ports"]:
        raise BootstrapFailure("ISOLATION_UNAVAILABLE: exact active NETNONE browser parent required",infra=True)
    # Supervisor capability; no flag or namespace comes from model output.
    adapter=SimpleNamespace(base_url=session.origin,supervised_runtime=session,manifest=SimpleNamespace(accounts={}))
    harness=PlaywrightHarness(adapter,bindings={},routes={"home":"/"})
    checks=[]
    case=SimpleNamespace(console_errors=[],requests=[],check=lambda tag,observed,expected:checks.append(observed==expected))
    stage="open_page"
    async def render():
        nonlocal stage
        page=await harness.page(case,1280,auto_navigate=False)
        stage="configure_page"
        page.set_default_timeout(max(1,min(15000,int(timeout_s*1000))))
        errors=[]
        page.on("console",lambda message:errors.append(True) if message.type=="error" else None)
        if require_api:
            from urllib.parse import urlsplit
            origin=urlsplit(session.origin)
            def api_response(response):
                url=urlsplit(response.url)
                return (url.scheme,url.netloc,url.path)==(origin.scheme,origin.netloc,"/api/health") and response.request.method=="GET"
            # The application itself must fetch its API during this navigation.
            # A supervisor request or a hardcoded "OK" string is not that chain.
            async with page.expect_response(api_response,timeout=max(1,int(timeout_s*1000))) as observed:
                stage="navigate_for_api"
                response=await page.goto(session.origin,wait_until="networkidle")
                stage="observe_api"
            health=await observed.value
            stage="read_api_json"
            if health.status!=200 or await health.json()!=expected_health:
                raise BootstrapFailure("Actual frontend API response differs from supervisor nonce-bound health")
        else:
            stage="navigate"
            response=await page.goto(session.origin,wait_until="networkidle")
        if response is None or response.status!=200:
            raise BootstrapFailure("Browser entrypoint does not return HTTP 200")
        stage="render_root"
        await page.wait_for_function("""() => {
            const root=document.getElementById('root');
            return root && root.childElementCount>0 && (root.innerText.trim() || root.querySelector('canvas,svg,img'));
        }""")
        if require_api:
            stage="render_api_status"
            await page.wait_for_function("() => /Frontend → API(?: → base de données)? : OK/.test(document.body.innerText)")
        if errors or case.console_errors or not all(checks):
            raise BootstrapFailure("Browser console/page/network violation observed (untrusted text withheld)")
        stage="attest_browser"
        environment=harness.browser_environment
        current=session.inspect_configuration()
        if (environment.get("host_chromium") is not False or environment.get("parent_id")!=parent
                or environment.get("network_mode")!="container:"+parent or environment.get("client_network_exposed") is not False
                or session._assert_owned()!=parent or current["container_id"]!=parent or current["network_mode"]!="none"
                or current["running"] is not True or current["published_ports"]):
            raise BootstrapFailure("ISOLATION_UNAVAILABLE: actual Docker browser receipt absent",infra=True)
        return "Chromium Docker: production UI rendered" + (" ; frontend → API probe OK" if require_api else "") + "; exact NETNONE parent " + parent
    try:
        return await asyncio.wait_for(render(),timeout=timeout_s)
    except asyncio.TimeoutError as exc:
        raise BootstrapFailure("Isolated browser preflight deadline exceeded",infra=True) from exc
    except BootstrapFailure:
        raise
    except Exception as exc:
        raise BootstrapFailure("ISOLATION_UNAVAILABLE: Docker browser preflight unavailable ("+stage+": "+type(exc).__name__+"; private driver output withheld)",infra=True) from None
    finally:
        await harness.close()
