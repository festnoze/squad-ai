"""ARCADE - tous les jeux de games/ derriere une seule origine.

Le launcher historique (games/global_launcher) demarre un serveur et un port par
jeu, puis ouvre un onglet dessus. Ici il n'y a qu'un processus, un port, une
origine: chaque jeu devient une route statique (/g/<id>/) et la console est une
SPA qui monte le jeu choisi dans une iframe. Ce que ce choix supprime:

  - l'allocation de port par jeu, donc les collisions avec un service tiers
  - les processus enfants a surveiller, a tuer, et les serveurs zombies
  - la sonde reseau qui devinait l'etat de chaque jeu (lente et ambigue)

Ce que ce choix garantit:

  - un seul jeu vivant a la fois, par construction: il n'y a qu'une iframe, et
    la retirer du DOM detruit sa boucle rAF, son contexte WebGL, son
    AudioContext et ses ecouteurs, sans cooperation du jeu
  - le retour a la console est instantane et ne recharge pas la page
  - console et jeux partagent l'origine, donc la console peut piloter le jeu
    (raccourci de sortie, sortie du pointer lock) sans y toucher une ligne

Usage: python arcade.py [--port 8088] [--no-open]
Aucune dependance: bibliotheque standard uniquement (3.10+).
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

HERE = Path(__file__).resolve().parent
GAMES_DIR = HERE.parent
DEFAULT_PORT = 8088
RESCAN_EVERY = 3.0

# sous-dossiers de games/ que le scan ignore
SKIP_DIRS = {HERE.name, "global_launcher", "node_modules", "dist", "__pycache__", "venv"}

# Windows fait resoudre les types MIME par la base de registre, ou .js finit
# regulierement en text/plain: le navigateur refuse alors les modules ES. On
# n'utilise donc pas mimetypes, la table est explicite.
MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".wasm": "application/wasm",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".bin": "application/octet-stream",
    ".woff2": "font/woff2",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}

SHELL_FILES = {
    "/app.js": ("app.js", MIME[".js"]),
    "/styles.css": ("styles.css", MIME[".css"]),
}


# --------------------------------------------------------------------------
# decouverte des jeux
# --------------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_text(path: Path, limit: int = 64_000) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def _readme_title_and_pitch(folder: Path) -> tuple[str, str]:
    """Premier titre `#` et premier vrai paragraphe: badges, tableaux et blocs
    de code ne sont pas un pitch."""
    text = _read_text(folder / "README.md")
    title = ""
    pitch: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not title:
            if line.startswith("# "):
                title = line[2:].strip()
            continue
        if not line:
            if pitch:
                break
            continue
        if line.startswith(("#", "!", "|", ">", "```", "---", "- ", "* ")):
            if pitch:
                break
            continue
        pitch.append(line)
    return title, " ".join(pitch)[:400]


def _hue(text: str) -> int:
    """Teinte stable par jeu: la console n'a aucun visuel a charger, elle
    genere la vignette a partir de l'identifiant."""
    value = 0
    for char in text:
        value = (value * 31 + ord(char)) & 0xFFFFFFFF
    return value % 360


class Game:
    def __init__(self, folder: Path):
        self.folder = folder
        self.id = folder.name
        meta = _read_json(folder / "arcade.json") or _read_json(folder / "launcher.json")
        pkg = _read_json(folder / "package.json")
        title, pitch = _readme_title_and_pitch(folder)

        self.name: str = meta.get("name") or title or folder.name
        self.description: str = meta.get("description") or pitch or pkg.get("description") or ""
        self.entry: str = meta.get("entry") or "index.html"
        self.accent: int = meta["accent"] if isinstance(meta.get("accent"), int) else _hue(self.id)

        # un projet avec un script `build` est servi depuis son dist/: son
        # index.html de racine est une source de bundler, pas une page servable
        scripts = pkg.get("scripts") if isinstance(pkg.get("scripts"), dict) else {}
        self.built = "build" in (scripts or {})
        self.root = folder / "dist" if self.built else folder
        self.build_hint = f"npm install && npm run build   (dans games/{folder.name})" if self.built else ""

        self.ready = (self.root / self.entry).is_file()
        self.stale = self._is_stale()

    def _is_stale(self) -> bool:
        """dist/ plus vieux que src/: le jeu tourne, mais pas la derniere version."""
        if not self.built or not self.ready:
            return False
        src = self.folder / "src"
        if not src.is_dir():
            return False
        built_at = (self.root / self.entry).stat().st_mtime
        try:
            return any(p.stat().st_mtime > built_at for p in src.rglob("*") if p.is_file())
        except OSError:
            return False

    @property
    def url(self) -> str:
        # un dossier de jeu peut contenir une espace ("Space Invader")
        return f"/g/{quote(self.id)}/{quote(self.entry)}"

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "accent": self.accent,
            "ready": self.ready,
            "stale": self.stale,
            "built": self.built,
            "buildHint": self.build_hint,
            "source": "dist" if self.built else "dossier",
        }


def discover_games() -> list[Game]:
    if not GAMES_DIR.is_dir():
        return []
    games: list[Game] = []
    for folder in sorted(GAMES_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not folder.is_dir() or folder.name in SKIP_DIRS or folder.name.startswith((".", "_")):
            continue
        # etre un jeu, c'est livrer un index.html: a la racine, ou dans dist/
        if not ((folder / "index.html").is_file() or (folder / "dist" / "index.html").is_file()):
            continue
        games.append(Game(folder))
    return games


# --------------------------------------------------------------------------
# serveur
# --------------------------------------------------------------------------


def _safe_join(root: Path, relative: str) -> Path | None:
    """Refuse tout ce qui sort du dossier du jeu (../, liens, chemins absolus)."""
    try:
        candidate = (root / relative).resolve()
        candidate.relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return candidate


class ArcadeHandler(BaseHTTPRequestHandler):
    server_version = "Arcade"
    protocol_version = "HTTP/1.1"

    # ---- primitives de reponse ----

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # tout est servi sans cache: sinon une modif de jeu reste invisible
        # derriere le cache de modules du navigateur
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), MIME[".json"])

    def _text_error(self, message: str, status: HTTPStatus) -> None:
        self._send(status, message.encode("utf-8"), MIME[".txt"])

    def _file(self, path: Path, content_type: str | None = None) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self._text_error(f"illisible: {path.name}", HTTPStatus.NOT_FOUND)
            return
        self._send(status=HTTPStatus.OK, body=body, content_type=content_type or MIME.get(path.suffix.lower(), "application/octet-stream"))

    # ---- routage ----

    def do_HEAD(self) -> None:  # noqa: N802 - nom impose par la classe de base
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802 - nom impose par la classe de base
        route = unquote(urlparse(self.path).path)

        if route == "/api/games":
            self.server.refresh()  # type: ignore[attr-defined]
            self._json({"games": [g.payload() for g in self.server.games]})  # type: ignore[attr-defined]
            return

        if route in SHELL_FILES:
            filename, content_type = SHELL_FILES[route]
            self._file(HERE / filename, content_type)
            return

        if route.startswith("/g/"):
            self._serve_game(route)
            return

        # "/" et "/play/<id>" rendent la meme SPA: c'est le client qui route
        if route == "/" or route == "/index.html" or route.startswith("/play/"):
            self._file(HERE / "index.html", MIME[".html"])
            return

        if self._rescue_absolute(route):
            return

        self._text_error(f"introuvable: {route}", HTTPStatus.NOT_FOUND)

    def _serve_game(self, route: str) -> None:
        rest = route[len("/g/") :]
        game_id, _, relative = rest.partition("/")
        game = self.server.game(game_id)  # type: ignore[attr-defined]
        if game is None:
            self._text_error(f"jeu inconnu: {game_id}", HTTPStatus.NOT_FOUND)
            return
        if not relative or relative.endswith("/"):
            relative += game.entry
        if not game.ready and relative == game.entry:
            self._text_error(
                f"{game.name} n'est pas construit.\n\n{game.build_hint}",
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return

        target = _safe_join(game.root, relative)
        if target is None or not target.is_file():
            self._text_error(f"introuvable: {relative}", HTTPStatus.NOT_FOUND)
            return
        self._file(target)

    def _rescue_absolute(self, route: str) -> bool:
        """Filet pour un jeu construit avec `base: '/'`: ses assets partent a la
        racine de l'origine. Le Referer dit de quel jeu vient la requete, on
        resout donc dans ce jeu la. Signale une fois par jeu, parce que la vraie
        correction est cote jeu (base relative au build)."""
        referer = urlparse(self.headers.get("Referer") or "").path
        found = re.match(r"/(?:g|play)/([^/]+)", referer)
        if not found:
            return False
        game = self.server.game(unquote(found.group(1)))  # type: ignore[attr-defined]
        if game is None:
            return False
        target = _safe_join(game.root, route.lstrip("/"))
        if target is None or not target.is_file():
            return False
        self.server.warn_absolute(game)  # type: ignore[attr-defined]
        self._file(target)
        return True

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - signature imposee
        # une console lisible: seuls les echecs sont interessants
        if len(args) > 1 and str(args[1]).startswith(("4", "5")):
            super().log_message(format, *args)


class ArcadeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int]):
        super().__init__(address, ArcadeHandler)
        self._lock = threading.Lock()
        self.games: list[Game] = discover_games()
        self._scanned_at = time.monotonic()
        self._warned: set[str] = set()

    def refresh(self) -> None:
        """Rescan complet et periodique. Contrairement au launcher historique,
        on reconstruit les objets: editer un arcade.json ou construire un dist/
        se voit sans redemarrer."""
        with self._lock:
            if time.monotonic() - self._scanned_at < RESCAN_EVERY:
                return
            self.games = discover_games()
            self._scanned_at = time.monotonic()

    def game(self, game_id: str) -> Game | None:
        return next((g for g in self.games if g.id == game_id), None)

    def warn_absolute(self, game: Game) -> None:
        if game.id in self._warned:
            return
        self._warned.add(game.id)
        print(
            f"  ! {game.name}: assets servis depuis la racine de l'origine.\n"
            f"    Le build utilise base: '/'. Ajouter base: './' dans vite.config.js\n"
            f"    puis rebuild, sinon le jeu ne marche que via ce filet."
        )


# --------------------------------------------------------------------------
# entree
# --------------------------------------------------------------------------


def _port_taken(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Console de jeux mono-origine.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true", help="ne pas ouvrir le navigateur")
    args = parser.parse_args()

    if _port_taken(args.port):
        print(f"Le port {args.port} est deja occupe. Relance avec --port <autre port>.")
        return 1

    server = ArcadeServer(("127.0.0.1", args.port))
    url = f"http://localhost:{args.port}/"

    print(f"ARCADE sur {url}")
    for game in server.games:
        state = "pret" if game.ready else "a construire"
        flag = " (dist perime)" if game.stale else ""
        print(f"  - {game.name:<22} /g/{game.id}/   [{state}{flag}]")
    if not server.games:
        print(f"  aucun jeu trouve dans {GAMES_DIR}")
    print("Ctrl+C pour arreter.")

    if not args.no_open:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\narret")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
