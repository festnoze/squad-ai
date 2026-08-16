"""GLOBAL LAUNCHER - console de lancement des jeux du dossier games/.

Scanne les dossiers voisins, en deduit le nom, le port et la commande de
serveur de chaque jeu, puis expose une petite UI web:

    python launcher.py [--port 8099] [--no-open]

Depuis l'UI, un clic sur un jeu demarre son serveur s'il ne tourne pas deja
(npm install compris si node_modules manque) et ouvre le jeu dans un nouvel
onglet une fois le port a l'ecoute.

Zero dependance: uniquement la bibliotheque standard.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
GAMES_DIR = HERE.parent
DEFAULT_LAUNCHER_PORT = 8099
FALLBACK_PORT_BASE = 8200
IS_WINDOWS = os.name == "nt"

# dossiers du repertoire games/ que le scan ignore
SKIP_DIRS = {HERE.name, "node_modules", "dist", "__pycache__"}

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}

# images de couverture cherchees dans chaque jeu, dans cet ordre
COVER_CANDIDATES = (
    "cover.png",
    "docs/cover.png",
    "docs/screenshot.png",
    "docs/screenshots/cover.png",
    "shots/smoke.png",
    "public/cover.png",
    ".smoke/ile.png",
)


# --------------------------------------------------------------------------
# detection des jeux
# --------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(_read_text(path))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _readme_title_and_pitch(folder: Path) -> tuple[str | None, str | None]:
    """Titre = premier '# ' du README, pitch = paragraphe qui le suit."""
    readme = next((folder / name for name in ("README.md", "readme.md") if (folder / name).is_file()), None)
    if readme is None:
        return None, None
    title, pitch_lines, seen_title = None, [], False
    for line in _read_text(readme).splitlines():
        stripped = line.strip()
        if not seen_title:
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                seen_title = True
            continue
        if not stripped:
            if pitch_lines:
                break
            continue
        if stripped.startswith(("#", "|", "```", "![", "> ")):
            break
        pitch_lines.append(stripped)
    pitch = " ".join(pitch_lines) if pitch_lines else None
    if pitch and len(pitch) > 260:
        pitch = pitch[:257].rsplit(" ", 1)[0] + "..."
    return title, pitch


def _script_of(pkg: dict[str, Any], keys: tuple[str, ...]) -> tuple[str | None, str | None]:
    scripts = pkg.get("scripts")
    if not isinstance(scripts, dict):
        return None, None
    for key in keys:
        value = scripts.get(key)
        if isinstance(value, str) and value.strip():
            return key, value.strip()
    return None, None


SERVER_SCRIPT_KEYS = ("dev", "start", "serve", "preview")


def _detect_port(folder: Path, pkg: dict[str, Any], meta: dict[str, Any]) -> int | None:
    if isinstance(meta.get("port"), int):
        return meta["port"]

    _, script = _script_of(pkg, SERVER_SCRIPT_KEYS)
    if script:
        for pattern in (r"--port[= ](\d{2,5})", r"http\.server\s+(\d{2,5})", r"-p\s+(\d{2,5})"):
            found = re.search(pattern, script)
            if found:
                return int(found.group(1))

    vite = folder / "vite.config.js"
    if vite.is_file():
        found = re.search(r"port:\s*(\d{2,5})", _read_text(vite))
        if found:
            return int(found.group(1))

    serve_py = folder / "serve.py"
    if serve_py.is_file():
        found = re.search(r"DEFAULT_PORT\s*=\s*(\d{2,5})", _read_text(serve_py))
        if found:
            return int(found.group(1))

    title_source = folder / "README.md"
    if title_source.is_file():
        found = re.search(r"localhost:(\d{4,5})", _read_text(title_source))
        if found:
            return int(found.group(1))

    return None


def _npm_command(args: list[str]) -> list[str]:
    """npm est un .cmd sous Windows: CreateProcess ne l'execute pas directement."""
    npm = shutil.which("npm") or "npm"
    if IS_WINDOWS and npm.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", npm, *args]
    return [npm, *args]


def _detect_command(folder: Path, port: int, pkg: dict[str, Any], meta: dict[str, Any]) -> tuple[list[str], str]:
    raw = meta.get("command")
    if isinstance(raw, str) and raw.strip():
        return shlex.split(raw), "launcher.json"
    if isinstance(raw, list) and raw:
        return [str(part) for part in raw], "launcher.json"

    key, script = _script_of(pkg, SERVER_SCRIPT_KEYS)
    if key and script:
        if re.match(r"^py(thon3?)?\b", script):
            return [sys.executable, *shlex.split(script)[1:]], f"package.json ({key})"
        return _npm_command(["run", key]), f"npm run {key}"

    if (folder / "serve.py").is_file():
        return [sys.executable, "serve.py", str(port)], "serve.py"

    return [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], "http.server"


def _detect_cover(folder: Path, meta: dict[str, Any]) -> str | None:
    candidates = list(COVER_CANDIDATES)
    if isinstance(meta.get("cover"), str):
        candidates.insert(0, meta["cover"])
    for rel in candidates:
        target = folder / rel
        if target.is_file():
            return rel
    return None


class Game:
    def __init__(self, folder: Path, index: int):
        self.folder = folder
        self.id = folder.name
        meta = _read_json(folder / "launcher.json")
        pkg = _read_json(folder / "package.json")
        title, pitch = _readme_title_and_pitch(folder)

        self.name: str = meta.get("name") or title or folder.name
        self.description: str = meta.get("description") or pitch or pkg.get("description") or ""
        self.port: int = _detect_port(folder, pkg, meta) or (FALLBACK_PORT_BASE + index)
        self.port_detected = _detect_port(folder, pkg, meta) is not None
        self.command, self.command_source = _detect_command(folder, self.port, pkg, meta)
        self.entry: str = meta.get("entry") or "index.html"
        self.cover = _detect_cover(folder, meta)
        # un projet npm avec des deps mais sans node_modules doit installer avant de servir
        self.install_command: list[str] | None = None
        has_deps = bool(pkg.get("dependencies") or pkg.get("devDependencies"))
        if has_deps and not (folder / "node_modules").is_dir():
            self.install_command = _npm_command(["install"])

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}/{self.entry}".rstrip("/")


def discover_games() -> list[Game]:
    games: list[Game] = []
    for index, folder in enumerate(sorted(p for p in GAMES_DIR.iterdir() if p.is_dir())):
        if folder.name in SKIP_DIRS or folder.name.startswith((".", "_")):
            continue
        if not (folder / "index.html").is_file():
            continue  # tous les jeux du dossier sont des jeux navigateur
        games.append(Game(folder, index))
    return games


# --------------------------------------------------------------------------
# supervision des serveurs
# --------------------------------------------------------------------------


def port_is_open(port: int, host: str = "localhost", timeout: float = 0.35) -> bool:
    """Vite ecoute souvent sur ::1 seulement, http.server sur 0.0.0.0: on teste
    toutes les adresses derriere le nom d'hote, pas seulement 127.0.0.1."""
    try:
        candidates = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for family, socktype, proto, _, address in candidates:
        with socket.socket(family, socktype, proto) as sock:
            sock.settimeout(timeout)
            if sock.connect_ex(address) == 0:
                return True
    return False


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(os.getpgid(proc.pid), 15)  # type: ignore[attr-defined]  # posix only
        except (ProcessLookupError, PermissionError, AttributeError):
            proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


class Supervisor:
    """Demarre, surveille et arrete les serveurs de jeu."""

    INSTALL_TIMEOUT = 300.0
    START_TIMEOUT = 90.0

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.procs: dict[str, subprocess.Popen] = {}
        self.states: dict[str, str] = {}
        self.details: dict[str, str] = {}
        self.logs: dict[str, deque[str]] = {}
        # jeux arretes pendant leur phase d'installation: le thread doit renoncer
        self.cancelled: set[str] = set()

    def log(self, game_id: str, line: str) -> None:
        self.logs.setdefault(game_id, deque(maxlen=200)).append(line.rstrip())

    def state_of(self, game: Game) -> tuple[str, str]:
        """running/external/starting/installing/error/stopped + un detail lisible."""
        proc = self.procs.get(game.id)
        state = self.states.get(game.id, "stopped")
        if state in ("installing", "starting"):
            return state, self.details.get(game.id, "")
        if proc is not None and proc.poll() is None:
            return ("running", "servi par le launcher") if port_is_open(game.port) else ("starting", "en attente du port")
        if port_is_open(game.port):
            return "external", "deja servi hors launcher"
        if state == "error":
            return "error", self.details.get(game.id, "echec du demarrage")
        return "stopped", ""

    def start(self, game: Game) -> dict[str, Any]:
        with self.lock:
            state, _ = self.state_of(game)
            if state in ("running", "external"):
                return {"state": state, "url": game.url}
            if state in ("installing", "starting"):
                return {"state": state, "url": game.url}
            self.states[game.id] = "installing" if game.install_command else "starting"
            self.details[game.id] = (
                "npm install en cours" if game.install_command else "demarrage du serveur"
            )
            self.logs[game.id] = deque(maxlen=200)
            self.cancelled.discard(game.id)

        threading.Thread(target=self._run, args=(game,), name=f"start-{game.id}", daemon=True).start()
        return {"state": self.states[game.id], "url": game.url}

    def _fail(self, game: Game, message: str) -> None:
        self.states[game.id] = "error"
        self.details[game.id] = message
        self.log(game.id, f"[launcher] {message}")

    def _run(self, game: Game) -> None:
        if game.install_command:
            self.log(game.id, f"[launcher] {' '.join(game.install_command)}")
            try:
                completed = subprocess.run(
                    game.install_command,
                    cwd=game.folder,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.INSTALL_TIMEOUT,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                self._fail(game, f"npm install a echoue: {exc}")
                return
            for line in (completed.stdout or "").splitlines()[-40:]:
                self.log(game.id, line)
            for line in (completed.stderr or "").splitlines()[-40:]:
                self.log(game.id, line)
            if completed.returncode != 0:
                self._fail(game, f"npm install a echoue (code {completed.returncode})")
                return
            game.install_command = None

        if game.id in self.cancelled:
            self.log(game.id, "[launcher] demarrage annule")
            return

        self.states[game.id] = "starting"
        self.details[game.id] = "demarrage du serveur"
        self.log(game.id, f"[launcher] {' '.join(game.command)} (cwd={game.folder})")
        creation = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
        try:
            proc = subprocess.Popen(
                game.command,
                cwd=game.folder,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation,
                start_new_session=not IS_WINDOWS,
            )
        except OSError as exc:
            self._fail(game, f"lancement impossible: {exc}")
            return

        with self.lock:
            self.procs[game.id] = proc
        threading.Thread(target=self._pump, args=(game.id, proc), daemon=True).start()

        deadline = time.monotonic() + self.START_TIMEOUT
        while time.monotonic() < deadline:
            if port_is_open(game.port):
                self.states[game.id] = "running"
                self.details[game.id] = "servi par le launcher"
                return
            if proc.poll() is not None:
                self._fail(game, f"le serveur s'est arrete (code {proc.returncode})")
                return
            time.sleep(0.4)
        self._fail(game, f"port {game.port} toujours muet apres {int(self.START_TIMEOUT)}s")

    def _pump(self, game_id: str, proc: subprocess.Popen) -> None:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            self.log(game_id, line)

    def stop(self, game: Game) -> dict[str, Any]:
        with self.lock:
            proc = self.procs.pop(game.id, None)
            self.cancelled.add(game.id)
        if proc is None:
            self.states[game.id] = "stopped"
            self.details[game.id] = ""
            return {"state": self.state_of(game)[0], "owned": False}
        _kill_tree(proc)
        self.states[game.id] = "stopped"
        self.details[game.id] = ""
        self.log(game.id, "[launcher] serveur arrete")
        return {"state": self.state_of(game)[0], "owned": True}

    def stop_all(self) -> None:
        with self.lock:
            procs = list(self.procs.items())
            self.procs.clear()
        for game_id, proc in procs:
            print(f"  arret de {game_id}")
            _kill_tree(proc)


SUPERVISOR = Supervisor()


# --------------------------------------------------------------------------
# serveur HTTP du launcher
# --------------------------------------------------------------------------


class LauncherHandler(BaseHTTPRequestHandler):
    server_version = "GlobalLauncher/1.0"

    # --- helpers ---------------------------------------------------------

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        self._json({"error": message}, status)

    def _game(self, game_id: str | None) -> Game | None:
        if not game_id:
            return None
        return next((g for g in self.server.games if g.id == game_id), None)  # type: ignore[attr-defined]

    def _payload(self, game: Game) -> dict[str, Any]:
        state, detail = SUPERVISOR.state_of(game)
        return {
            "id": game.id,
            "name": game.name,
            "description": game.description,
            "port": game.port,
            "portDetected": game.port_detected,
            "url": game.url,
            "folder": game.folder.name,
            "command": " ".join(game.command),
            "commandSource": game.command_source,
            "needsInstall": game.install_command is not None,
            "hasCover": game.cover is not None,
            "state": state,
            "detail": detail,
        }

    # --- routes ----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - nom impose par BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        route, query = parsed.path, parse_qs(parsed.query)

        if route in STATIC_FILES:
            filename, content_type = STATIC_FILES[route]
            target = HERE / filename
            if not target.is_file():
                self._error(f"{filename} introuvable", HTTPStatus.NOT_FOUND)
                return
            self._send(HTTPStatus.OK, target.read_bytes(), content_type)
            return

        if route == "/api/games":
            self.server.refresh_games()  # type: ignore[attr-defined]
            self._json({"games": [self._payload(g) for g in self.server.games]})  # type: ignore[attr-defined]
            return

        if route == "/api/logs":
            game = self._game((query.get("id") or [None])[0])
            if game is None:
                self._error("jeu inconnu", HTTPStatus.NOT_FOUND)
                return
            self._json({"id": game.id, "lines": list(SUPERVISOR.logs.get(game.id, []))})
            return

        if route == "/api/cover":
            game = self._game((query.get("id") or [None])[0])
            if game is None or game.cover is None:
                self._error("pas de visuel", HTTPStatus.NOT_FOUND)
                return
            target = (game.folder / game.cover).resolve()
            if not target.is_file() or game.folder.resolve() not in target.parents:
                self._error("pas de visuel", HTTPStatus.NOT_FOUND)
                return
            self._send(HTTPStatus.OK, target.read_bytes(), "image/png")
            return

        self._error("route inconnue", HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - nom impose par BaseHTTPRequestHandler
        route = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._error("corps JSON invalide")
            return

        game = self._game(body.get("id") if isinstance(body, dict) else None)
        if game is None:
            self._error("jeu inconnu", HTTPStatus.NOT_FOUND)
            return

        if route == "/api/launch":
            result = SUPERVISOR.start(game)
            self._json({**self._payload(game), **result})
            return
        if route == "/api/stop":
            SUPERVISOR.stop(game)
            self._json(self._payload(game))
            return

        self._error("route inconnue", HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - signature imposee
        if len(args) > 1 and str(args[1]).startswith(("4", "5")):
            super().log_message(format, *args)


class LauncherServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int]):
        super().__init__(address, LauncherHandler)
        self.games: list[Game] = discover_games()
        self._scanned_at = time.monotonic()

    def refresh_games(self) -> None:
        """Rescan periodique: un jeu ajoute dans games/ apparait sans redemarrage."""
        if time.monotonic() - self._scanned_at < 5.0:
            return
        known = {g.id for g in self.games}
        fresh = discover_games()
        if {g.id for g in fresh} != known:
            # on garde les instances connues (elles portent l'etat d'install) et
            # on ajoute seulement les nouveaux dossiers
            by_id = {g.id: g for g in self.games}
            self.games = [by_id.get(g.id, g) for g in fresh]
        self._scanned_at = time.monotonic()


def main() -> int:
    parser = argparse.ArgumentParser(description="Console de lancement des jeux de games/")
    parser.add_argument("--port", type=int, default=DEFAULT_LAUNCHER_PORT, help="port du launcher")
    parser.add_argument("--no-open", action="store_true", help="ne pas ouvrir le navigateur au demarrage")
    args = parser.parse_args()

    if port_is_open(args.port):
        print(f"Le port {args.port} est deja occupe. Relance avec --port <autre port>.")
        return 1

    ThreadingHTTPServer.allow_reuse_address = True
    server = LauncherServer(("127.0.0.1", args.port))
    url = f"http://localhost:{args.port}/"
    print(f"GLOBAL LAUNCHER sur {url}")
    print(f"Jeux detectes dans {GAMES_DIR}:")
    for game in server.games:
        print(f"  - {game.name} ({game.id}) port {game.port} via {game.command_source}")
    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open_new_tab(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\narret du launcher")
    finally:
        SUPERVISOR.stop_all()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
