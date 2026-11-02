"""Hidden oracle of B5 (relais_support): the 57 criteria of
docs/validation/support-client/02_requirements_verification.md.

Only the part of a criterion that is observable from outside the product is automated,
through the interface fixed by bench/briefs/B5-relais-support.md (section 7 of the
specification plus the bench annex: commands, environment variables, JSON names). The
product is driven over HTTP; the only other contacts are the `create-admin` command of
the annex and a read-only byte scan (plus one held lock, ARC-03) of the SQLite file the
annex places at RELAIS_DB. Every criterion that cannot be judged that way is returned
failed with detail NOT_AUTOMATED, so the rate stays honest. bench/oracles/B5_COVERAGE.md
says, per criterion, what is checked and what is not.

Order matters: failed logins are rate limited per IP (10 per 60 s window), so the main
phase makes at most 5 failed logins and SEC-04 (failures, then the rate limit) runs on a
fresh server and database (phase 3).
"""

from __future__ import annotations

import email.utils
import http.client
import json
import re
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from bench import proc
from bench.oracle import NOT_AUTOMATED, Check, Product, Server

HEALTH_PATH = "/api/health"

CRITERIA: list[str] = (
    [f"SEC-{i:02d}" for i in range(1, 16)] + [f"FUN-{i:02d}" for i in range(1, 14)]
    + [f"ARC-{i:02d}" for i in range(1, 10)] + [f"UX-{i:02d}" for i in range(1, 9)]
    + [f"TST-{i:02d}" for i in range(1, 7)] + [f"OPS-{i:02d}" for i in range(1, 7)]
)

# Why each of these is not automated: bench/oracles/B5_COVERAGE.md.
NOT_AUTOMATED_IDS = frozenset({
    "FUN-08", "ARC-01", "ARC-02", "ARC-04", "ARC-05", "ARC-09",
    "UX-01", "UX-02", "UX-03", "UX-04", "UX-05", "UX-06", "UX-07",
    "TST-01", "TST-02", "TST-03", "TST-04", "TST-05", "TST-06",
    "OPS-02", "OPS-05", "OPS-06",
})

ADMIN_EMAIL = "admin@relais.test"
ADMIN_NAME = "Administratrice Relais"
ADMIN_PASSWORD = "Phrase de passe admin 2026 !"
SECRET = "NOTE-INTERNE-B5-SECRETE"
STATUSES = ("open", "in_progress", "resolved", "closed")
ERROR_STATUSES = (401, 403, 404, 409, 422, 429, 503)
SPEC_ROUTES = [
    ("POST", "/api/auth/login"), ("POST", "/api/auth/logout"), ("GET", "/api/auth/me"),
    ("GET", "/api/users"), ("POST", "/api/users"), ("PATCH", "/api/users/{}"), ("GET", "/api/assignees"),
    ("GET", "/api/tickets"), ("POST", "/api/tickets"), ("GET", "/api/tickets/{}"), ("PATCH", "/api/tickets/{}"),
    ("GET", "/api/tickets/{}/messages"), ("POST", "/api/tickets/{}/messages"),
    ("GET", "/api/tickets/{}/history"), ("GET", "/api/dashboard"),
]
_ARGON2 = re.compile(rb"\$argon2id\$v=\d+\$m=(\d+),t=(\d+),p=(\d+)\$[A-Za-z0-9+/]+\$[A-Za-z0-9+/]+")
_LEAK = re.compile(r"Traceback \(most recent call last\)|File \"[^\"]+\", line \d+|sqlite3\.\w+|"
                   r"OperationalError|IntegrityError|\bSELECT\b.+\bFROM\b|\bINSERT INTO\b")
_BACKEND_URL = re.compile(r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?/api|(?:localhost|127\.0\.0\.1):8000")
_SCRIPT = re.compile(r"""<(?:script|link)[^>]+(?:src|href)\s*=\s*["']([^"']+\.js)["']""", re.IGNORECASE)
_UNSET = object()


class Fail(Exception):
    """A check failed; the message becomes the Check detail."""


def expect(condition: object, detail: str) -> None:
    if not condition:
        raise Fail(detail)


# --------------------------------------------------------------------------- HTTP


@dataclass
class Resp:
    status: int
    body: object
    text: str
    headers: list[tuple[str, str]]
    elapsed_s: float = 0.0

    def header(self, name: str) -> str:
        name = name.lower()
        return next((v for k, v in self.headers if k.lower() == name), "")

    def set_cookies(self) -> list["SetCookie"]:
        return [parse_set_cookie(v) for k, v in self.headers if k.lower() == "set-cookie"]

    def item(self, key: str) -> object:
        return self.body.get(key) if isinstance(self.body, dict) else None

    @property
    def error(self) -> dict:
        err = self.item("error")
        return err if isinstance(err, dict) else {}

    @property
    def code(self) -> str:
        return str(self.error.get("code", ""))

    def __str__(self) -> str:
        return f"{self.status} {self.text[:160]}"


@dataclass
class SetCookie:
    name: str
    value: str
    attrs: dict[str, str]  # lowercased attribute names; flags map to ""

    @property
    def expired(self) -> bool:
        max_age = self.attrs.get("max-age", "").strip()
        if re.fullmatch(r"-?\d+", max_age) and int(max_age) <= 0:
            return True
        expires = self.attrs.get("expires")
        if expires:
            try:
                return email.utils.parsedate_to_datetime(expires).timestamp() < time.time()
            except (TypeError, ValueError, IndexError):
                return False
        return False


def parse_set_cookie(header: str) -> SetCookie:
    parts = [part.strip() for part in header.split(";")]
    name, _, value = parts[0].partition("=")
    attrs: dict[str, str] = {}
    for part in parts[1:]:
        key, _, val = part.partition("=")
        attrs[key.strip().lower()] = val.strip()
    return SetCookie(name.strip(), value.strip().strip('"'), attrs)


def find_key(obj: object, key: str) -> object:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        obj = list(obj.values())
    if isinstance(obj, list):
        for value in obj:
            found = find_key(value, key)
            if found is not None:
                return found
    return None


@dataclass
class Actor:
    email: str
    password: str
    role: str
    name: str = ""
    id: str = ""
    cookies: dict[str, str] = field(default_factory=dict)
    csrf: str = ""

    def fresh(self, password: str | None = None) -> "Actor":
        """Same account, no session (or another password for a failing attempt)."""
        return Actor(self.email, self.password if password is None else password, self.role, self.name, self.id)

    def snapshot(self) -> "Actor":
        """A copy holding the current session, kept to replay it later."""
        return Actor(self.email, self.password, self.role, self.name, self.id, dict(self.cookies), self.csrf)


class Api:
    def __init__(self, port: int, origin: str) -> None:
        self.port = port
        self.origin = origin
        self.errors: list[tuple[str, str, Resp]] = []  # every 4xx/5xx seen (error format, leaks)
        self._lock = threading.Lock()

    def call(self, method: str, path: str, body: object = _UNSET, *, actor: Actor | None = None,
             params: dict | None = None, origin: object = _UNSET, csrf: object = _UNSET,
             headers: dict | None = None, timeout: float = 15.0) -> Resp:
        if params:
            path = f"{path}?{urlencode(params)}"
        mutation = method not in ("GET", "HEAD", "OPTIONS")
        sent = {"Accept": "application/json"}
        if origin is _UNSET:
            origin = self.origin if mutation else None
        if origin is not None:
            sent["Origin"] = str(origin)
        if actor is not None and actor.cookies:
            sent["Cookie"] = "; ".join(f"{k}={v}" for k, v in actor.cookies.items())
        if csrf is _UNSET:
            csrf = actor.csrf if (actor is not None and mutation) else None
        if csrf:
            sent["X-CSRF-Token"] = str(csrf)
        data = None
        if body is not _UNSET:
            data = json.dumps(body).encode("utf-8")
            sent["Content-Type"] = "application/json"
        sent.update(headers or {})
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        started = time.monotonic()
        try:
            conn.request(method, path, body=data, headers=sent)
            raw = conn.getresponse()
            text = raw.read().decode("utf-8", errors="replace")
            resp = Resp(raw.status, None, text, list(raw.getheaders()), round(time.monotonic() - started, 3))
        finally:
            conn.close()
        try:
            resp.body = json.loads(text) if text else None
        except json.JSONDecodeError:
            resp.body = text
        if resp.status >= 400:
            with self._lock:
                self.errors.append((method, path, resp))
        return resp


# --------------------------------------------------------------------------- world


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


class World:
    """Shared state of one oracle run: the server, the accounts, the tickets created."""

    def __init__(self, product: Product, db: Path) -> None:
        self.product = product
        self.db = db
        self.api: Api | None = None
        self.actors: dict[str, Actor] = {}
        self.tickets: dict[str, set[str]] = defaultdict(set)  # owner email -> ids answered 201
        self.facts: dict[str, object] = {}

    # -- process level
    def bootstrap(self, *, credentials: bool, admin_email: str = ADMIN_EMAIL) -> object:
        env = self.product.env(RELAIS_DB=str(self.db))
        for name in ("RELAIS_ADMIN_EMAIL", "RELAIS_ADMIN_NAME", "RELAIS_ADMIN_PASSWORD"):
            env.pop(name, None)
        if credentials:
            env.update(RELAIS_ADMIN_EMAIL=admin_email, RELAIS_ADMIN_NAME=ADMIN_NAME,
                       RELAIS_ADMIN_PASSWORD=ADMIN_PASSWORD)
        result = self.product.run(["-m", self.product.package, "create-admin"], env=env, timeout_s=90)
        if ADMIN_PASSWORD in result.stdout + result.stderr:
            self.facts["bootstrap_leak"] = True
        return result

    def server(self) -> Server:
        port = proc.free_port()
        origin = f"http://127.0.0.1:{port}"
        self.api = Api(port, origin)
        return Server(self.product, port=port, health_path=HEALTH_PATH,
                      extra_env={"RELAIS_DB": str(self.db), "RELAIS_ORIGIN": origin})

    def db_bytes(self) -> bytes:
        """Raw bytes of the database file and its journals (read only, format agnostic).

        On Windows the running server may hold the WAL without read sharing: SQLite's own
        online backup (which includes the committed WAL content) is then read instead.
        """
        data = b""
        locked = False
        for suffix in ("", "-wal", "-journal"):
            path = Path(f"{self.db}{suffix}")
            if path.is_file():
                try:
                    data += path.read_bytes()
                except PermissionError:
                    locked = True
        if locked:
            import sqlite3
            copy = Path(f"{self.db}.oracle-backup")
            source = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
            target = sqlite3.connect(copy)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
            data += copy.read_bytes()
            copy.unlink(missing_ok=True)
        return data

    # -- HTTP helpers
    def call(self, method: str, path: str, *args, **kwargs) -> Resp:
        resp = self.api.call(method, path, *args, **kwargs)
        actor = kwargs.get("actor")
        if method == "POST" and path == "/api/tickets" and resp.status == 201 and actor is not None                 and resp.item("id") is not None:  # every ticket created, even by a request meant to fail
            self.tickets[actor.email].add(str(resp.item("id")))
        return resp

    def a(self, name: str) -> Actor:
        return self.actors[name]

    @property
    def admin(self) -> Actor:
        return self.actors["admin"]

    @property
    def staff(self) -> Actor:
        return self.actors["camille"]

    def login(self, actor: Actor, **kwargs) -> Resp:
        resp = self.call("POST", "/api/auth/login", {"email": actor.email, "password": actor.password}, **kwargs)
        if resp.status == 200:
            actor.cookies = {c.name: c.value for c in resp.set_cookies() if c.value and not c.expired}
            actor.csrf = str(find_key(resp.body, "csrf_token") or "")
            user = resp.item("user")
            if isinstance(user, dict) and user.get("id") is not None:
                actor.id = str(user["id"])
        return resp

    def must_login(self, actor: Actor) -> None:
        resp = self.login(actor)
        expect(resp.status == 200 and actor.cookies and actor.csrf,
               f"login of {actor.email} -> {resp} (cookie and csrf_token expected)")

    def create_user(self, email_: str, name: str, password: str, role: str, *, actor: Actor | None = None,
                    extra: dict | None = None) -> Resp:
        body = {"email": email_, "display_name": name, "password": password, "role": role, **(extra or {})}
        return self.call("POST", "/api/users", body, actor=actor or self.admin)

    def add_user(self, key: str, role: str) -> Actor:
        actor = Actor(f"{key}@relais.test", f"Phrase de passe {key} 2026 !", role, f"Compte {key}")
        resp = self.create_user(actor.email, actor.name, actor.password, role)
        expect(resp.status == 201 and resp.item("id") is not None, f"admin creates {actor.email} -> {resp}")
        actor.id = str(resp.item("id"))
        self.must_login(actor)
        self.actors[key] = actor
        return actor

    def set_active(self, user_id: str, active: bool, actor: Actor | None = None) -> Resp:
        return self.call("PATCH", f"/api/users/{user_id}", {"active": active}, actor=actor or self.admin)

    def post_ticket(self, actor: Actor, *, title: str | None = None, description: str | None = None,
                    key: str | None = None, extra: dict | None = None, timeout: float = 15.0) -> Resp:
        body = {"title": "Imprimante du deuxième étage en panne" if title is None else title,
                "description": ("L'imprimante affiche une erreur de bac depuis ce matin."
                                if description is None else description),
                "client_request_id": key or str(uuid.uuid4()), **(extra or {})}
        return self.call("POST", "/api/tickets", body, actor=actor, timeout=timeout)

    def ticket(self, actor: Actor, **kwargs) -> str:
        resp = self.post_ticket(actor, **kwargs)
        expect(resp.status == 201 and resp.item("id") is not None, f"{actor.email} creates a ticket -> {resp}")
        return str(resp.item("id"))

    def get(self, tid: str, actor: Actor | None = None) -> dict:
        resp = self.call("GET", f"/api/tickets/{tid}", actor=actor or self.staff)
        expect(resp.status == 200 and isinstance(resp.body, dict), f"GET ticket -> {resp}")
        return resp.body

    def version(self, tid: str) -> object:
        return self.get(tid).get("version")

    def patch(self, actor: Actor, tid: str, *, version: object = _UNSET, **fields) -> Resp:
        if version is _UNSET:
            version = self.version(tid)
        return self.call("PATCH", f"/api/tickets/{tid}", {"expected_version": version, **fields}, actor=actor)

    def message(self, actor: Actor, tid: str, body: str, visibility: str = "public", *, key: str | None = None,
                extra: dict | None = None) -> Resp:
        payload = {"body": body, "visibility": visibility, "client_request_id": key or str(uuid.uuid4()),
                   **(extra or {})}
        return self.call("POST", f"/api/tickets/{tid}/messages", payload, actor=actor)

    def page(self, actor: Actor, path: str, **params) -> Resp:
        resp = self.call("GET", path, actor=actor, params=params or None)
        expect(resp.status == 200 and isinstance(resp.body, dict) and isinstance(resp.item("items"), list)
               and isinstance(resp.item("total"), int), f"GET {path} {params} -> {resp}")
        return resp

    def total(self, actor: Actor, path: str, **params) -> int:
        return self.page(actor, path, **params).body["total"]

    def items(self, actor: Actor, path: str, **params) -> list[dict]:
        found: list[dict] = []
        for number in range(1, 60):
            resp = self.page(actor, path, **{**params, "page": number, "page_size": 50})
            batch = resp.body["items"]
            found += batch
            if not batch or len(found) >= resp.body["total"]:
                break
        return found

    def ids(self, actor: Actor, path: str, **params) -> set[str]:
        return {str(item.get("id")) for item in self.items(actor, path, **params)}

    def history_total(self, tid: str) -> int:
        return self.total(self.staff, f"/api/tickets/{tid}/history")

    def drive(self, tid: str, target: str) -> dict:
        """Move a ticket forward along the nominal path with the staff account."""
        staff = self.staff
        for _ in range(4):
            current = self.get(tid)
            status = current.get("status")
            if status == target:
                return current
            expect(status in STATUSES and STATUSES.index(status) < STATUSES.index(target),
                   f"cannot drive a {status} ticket to {target}")
            if status == "open":
                if current.get("assignee_id") is None:
                    resp = self.patch(staff, tid, assignee_id=staff.id)
                    expect(resp.status == 200, f"assign before in_progress -> {resp}")
                resp = self.patch(staff, tid, status="in_progress")
            elif status == "in_progress":
                reply = self.message(staff, tid, "Réponse publique de l'équipe support.")
                expect(reply.status == 201, f"public staff reply -> {reply}")
                resp = self.patch(staff, tid, status="resolved")
            else:
                resp = self.patch(staff, tid, status="closed")
            expect(resp.status == 200, f"drive {status} toward {target} -> {resp}")
        raise Fail(f"could not drive the ticket to {target}")

    @staticmethod
    def concurrently(fns: list[Callable[[], Resp]]) -> list[Resp]:
        """Run the calls from a synchronized start (threads behind a barrier)."""
        barrier = threading.Barrier(len(fns), timeout=30)
        out: list = [None] * len(fns)
        errors: list[BaseException] = []

        def worker(index: int, fn: Callable[[], Resp]) -> None:
            try:
                barrier.wait()
                out[index] = fn()
            except BaseException as exc:  # reported to the check
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i, fn), daemon=True) for i, fn in enumerate(fns)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=90)
        if errors:
            raise errors[0]
        expect(all(r is not None for r in out), "a concurrent call did not finish")
        return out

    # -- setup
    def setup_admin(self) -> str:
        """Log the bootstrap admin in. Returns "" or the reason why it is impossible."""
        admin = Actor(ADMIN_EMAIL, ADMIN_PASSWORD, "admin", ADMIN_NAME)
        try:
            resp = self.login(admin)
            if resp.status != 200 or not admin.cookies:
                return f"bootstrap admin cannot log in: {resp}"
            self.actors["admin"] = admin
            self.facts["admin_login"] = resp
            self.facts["admin_me"] = self.call("GET", "/api/auth/me", actor=admin)
            self.facts["initial_users"] = self.call("GET", "/api/users", actor=admin)
        except Exception as exc:  # any surprise here blocks the dependent checks, never the run
            return f"bootstrap admin: {exc}"
        return ""

    def setup_users(self) -> str:
        try:
            for key, role in (("alice", "client"), ("bob", "client"), ("camille", "agent"),
                              ("dylan", "agent"), ("emma", "admin")):
                self.add_user(key, role)
        except Exception as exc:  # any surprise here blocks the dependent checks, never the run
            return f"account setup: {exc}"
        return ""


def _problems(problems: list[str]) -> None:
    expect(not problems, "; ".join(problems[:6]) + (f" (+{len(problems) - 6})" if len(problems) > 6 else ""))


def _no_secret_keys(obj: dict) -> list[str]:
    return [k for k in obj if any(word in k.lower() for word in ("password", "hash", "session", "token"))]


# --------------------------------------------------------------------------- SEC


def sec_01(w: World) -> None:
    f = w.facts
    expect(f.get("bootstrap_no_credentials_rc") not in (0, None),
           f"create-admin without credentials (stdin closed) -> rc={f.get('bootstrap_no_credentials_rc')}, "
           "expected a refusal")
    expect(f.get("bootstrap_rc") == 0, f"create-admin with RELAIS_ADMIN_* -> rc={f.get('bootstrap_rc')}")
    expect(f.get("bootstrap_again_rc") not in (0, None),
           f"second create-admin when an admin exists -> rc={f.get('bootstrap_again_rc')}, expected a refusal")
    expect(not f.get("bootstrap_leak"), "create-admin prints the password")
    initial = f.get("initial_users")
    expect(isinstance(initial, Resp) and initial.status == 200 and initial.item("total") == 1,
           f"blank base + create-admin: GET /api/users -> {initial}, expected exactly one account")
    for resp in (f.get("admin_login"), f.get("admin_me")):
        expect(isinstance(resp, Resp) and ADMIN_PASSWORD not in resp.text and "$argon2" not in resp.text,
               f"authentication response exposes the password or its hash: {resp}")
    for user in w.items(w.admin, "/api/users"):
        bad = [k for k in user if "password" in k.lower() or "hash" in k.lower()]
        expect(not bad, f"account DTO exposes {bad}")


def sec_02(w: World) -> None:
    first = w.create_user(" Sec02@Example.TEST ", "Doublon un", "Phrase de passe doublon 2026", "client")
    expect(first.status == 201, f"create ' Sec02@Example.TEST ' -> {first}")
    expect(first.item("email") == "sec02@example.test", f"email stored as {first.item('email')!r}, expected "
           "'sec02@example.test' (trim + lower case)")
    dup = w.create_user("sec02@example.test", "Doublon deux", "Phrase de passe doublon 2026", "agent")
    expect(dup.status == 409, f"same normalized email -> {dup}, expected 409")
    off = w.set_active(str(first.item("id")), False)
    expect(off.status == 200, f"deactivate -> {off}")
    dup = w.create_user("SEC02@example.test", "Doublon trois", "Phrase de passe doublon 2026", "client")
    expect(dup.status == 409, f"same email as a deactivated account -> {dup}, expected 409")
    emails = [u.get("email") for u in w.items(w.admin, "/api/users")]
    expect(emails.count("sec02@example.test") == 1, f"{emails.count('sec02@example.test')} accounts for one email")
    racing = w.concurrently([
        lambda: w.create_user("race02@example.test", "Course A", "Phrase de passe course 2026", "client"),
        lambda: w.create_user(" RACE02@example.test", "Course B", "Phrase de passe course 2026", "client"),
    ])
    statuses = sorted(r.status for r in racing)
    expect(statuses == [201, 409], f"two simultaneous creations of one email -> {statuses}, expected [201, 409]")


def sec_03(w: World) -> None:
    problems: list[str] = []
    base = "Mot de passe long 0123456789 " * 6
    long_pw = base[:128]
    for size, expected in ((13, 422), (14, 201), (128, 201), (129, 422)):
        resp = w.create_user(f"sec03-{size}@relais.test", f"Longueur {size}", base[:size], "client")
        if resp.status != expected:
            problems.append(f"password of {size} characters -> {resp.status}, expected {expected}")
        elif resp.status == 201 and isinstance(resp.body, dict):
            problems += [f"account DTO exposes {k}" for k in resp.body if "password" in k.lower() or "hash" in k.lower()]
    spaced = "  espace é ü ß 漢字 🔒 fin  "
    resp = w.create_user("sec03-unicode@relais.test", "Unicode", spaced, "client")
    expect(resp.status == 201, f"password with spaces and unicode -> {resp}")
    unicode_user = Actor("sec03-unicode@relais.test", spaced, "client")
    expect(w.login(unicode_user).status == 200, "login with the exact spaced unicode password fails")
    trimmed = w.login(unicode_user.fresh(spaced.strip()))
    if trimmed.status != 401:
        problems.append(f"login with the password trimmed -> {trimmed.status}: the password is normalized")
    holder = Actor("sec03-128@relais.test", long_pw, "client")
    if w.login(holder).status != 200:
        problems.append("login with the exact 128 character password fails")
    variant = long_pw[:72] + "x" * 56
    if w.login(holder.fresh(variant)).status != 401:
        problems.append("a password that differs only after 72 characters is accepted: truncation")
    twin = "Phrase jumelle identique 2026"
    for key in ("sec03-twin-a", "sec03-twin-b"):
        resp = w.create_user(f"{key}@relais.test", key, twin, "client")
        if resp.status != 201:
            problems.append(f"create {key} -> {resp.status}")
    blob = w.db_bytes()
    expect(blob, f"database file {w.db.name} (RELAIS_DB) missing or empty")
    for secret in (spaced, long_pw, twin, ADMIN_PASSWORD):
        if secret.encode("utf-8") in blob:
            problems.append("a password is stored in clear in the database file")
            break
    hashes = {m.group(0) for m in _ARGON2.finditer(blob)}
    weak = [m.group(0)[:40] for m in _ARGON2.finditer(blob) if int(m.group(1)) < 19456 or int(m.group(2)) < 2]
    users = w.total(w.admin, "/api/users")
    if not hashes:
        problems.append("no $argon2id$ hash in the database file")
    elif weak:
        problems.append(f"argon2id parameters under m=19456,t=2: {weak[0]!r}")
    elif len(hashes) < users:
        problems.append(f"{len(hashes)} distinct argon2id hashes for {users} accounts: identical passwords share a hash")
    _problems(problems)


def sec_04(w: World) -> None:
    """Fresh server and database: identical failures, then 10 failures per IP in 60 s -> 429.

    Half of the failures carry a forged X-Forwarded-For: the product has no trusted proxy,
    so they must count for the real peer (127.0.0.1). Note that uvicorn trusts proxy headers
    from 127.0.0.1 by default (forwarded_allow_ips), which this probe reports.
    """
    client = w.add_user("sec04", "client")
    inactive = w.add_user("sec04-off", "client")
    expect(w.set_active(inactive.id, False).status == 200, "deactivate sec04-off")
    answers = {
        "wrong password": w.login(client.fresh(client.password + "x")),
        "unknown email": w.login(Actor("inconnu-sec04@relais.test", "Phrase inconnue 2026 !", "client")),
        "deactivated account": w.login(inactive.fresh()),
    }
    bad = [f"{name} -> {r.status}" for name, r in answers.items() if r.status != 401]
    expect(not bad, ", ".join(bad) + " (expected 401)")
    shapes = {(r.code, r.error.get("message")) for r in answers.values()}
    expect(len(shapes) == 1, f"login failures are distinguishable: {sorted(map(str, shapes))}")
    wrong = client.fresh(client.password + "!")
    failures = list(answers.values()) + [w.login(wrong) for _ in range(2)]
    success = w.login(client.fresh())
    failures += [w.login(wrong, headers={"X-Forwarded-For": f"203.0.113.{i}"}) for i in range(1, 6)]
    final = w.login(client.fresh())
    statuses = [r.status for r in failures]
    expect(all(status == 401 for status in statuses), f"the 10 failures answered {statuses}, expected 401 each")
    expect(success.status == 200, f"correct login after 5 failures -> {success.status}")
    if final.status != 429:
        probe = [w.login(wrong) for _ in range(5)]
        limited = w.login(client.fresh()).status == 429 or any(r.status == 429 for r in probe)
        raise Fail(f"correct login after 10 failures in 60 s (5 of them with a forged X-Forwarded-For, one "
                   f"success in between) -> {final.status}, expected 429; " +
                   ("the limit exists but counts the forged X-Forwarded-For as the client address (uvicorn "
                    "trusts proxy headers from 127.0.0.1 unless proxy_headers=False)" if limited
                    else "no rate limit observed"))
    expect(final.header("Retry-After"), "429 without a Retry-After header")


def sec_05(w: World) -> None:
    first, second = w.admin.fresh(), w.admin.fresh()
    r1, r2 = w.login(first), w.login(second)
    expect(r1.status == 200 and r2.status == 200, f"logins -> {r1.status}, {r2.status}")
    session = [c for c in r1.set_cookies() if "httponly" in c.attrs and c.value]
    expect(session, f"login sets no HttpOnly cookie: {[c.name for c in r1.set_cookies()]}")
    cookie = session[0]
    expect(cookie.attrs.get("samesite", "").lower() == "lax", f"SameSite={cookie.attrs.get('samesite')!r}")
    expect(cookie.attrs.get("path") == "/", f"Path={cookie.attrs.get('path')!r}")
    expect(len(cookie.value) >= 43, f"session token of {len(cookie.value)} characters: under 256 bits")
    expect(first.cookies.get(cookie.name) != second.cookies.get(cookie.name), "two logins share one token")
    expect(cookie.value not in r1.text, "the session token is readable in the login body")
    max_age = cookie.attrs.get("max-age", "")
    expect(not max_age.isdigit() or int(max_age) <= 8 * 3600, f"cookie Max-Age={max_age} beyond 8 h")
    blob = w.db_bytes()
    expect(blob, "database file (RELAIS_DB) missing or empty")
    expect(cookie.value.encode("utf-8") not in blob, "the raw session token is stored in the database")


def sec_06(w: World) -> None:
    user = w.add_user("sec06", "client")
    old = user.snapshot()
    out = w.call("POST", "/api/auth/logout", actor=user)
    expect(out.status == 204, f"logout -> {out}")
    expect(any(c.expired for c in out.set_cookies()), "logout does not expire the cookie")
    expect(w.call("GET", "/api/auth/me", actor=old).status == 401, "session still valid after logout")
    again = w.call("POST", "/api/auth/logout", actor=old)
    expect(again.status == 204 and any(c.expired for c in again.set_cookies()),
           f"logout without a valid session -> {again.status}, expected 204 with an expired cookie")
    blind = w.call("POST", "/api/auth/logout", actor=old, origin=None)
    expect(blind.status == 403, f"logout without Origin -> {blind.status}, expected 403")
    other = w.add_user("sec06b", "client")
    kept = other.snapshot()
    expect(w.set_active(other.id, False).status == 200, "deactivate")
    expect(w.call("GET", "/api/auth/me", actor=kept).status == 401, "session survives deactivation")
    expect(w.set_active(other.id, True).status == 200, "reactivate")
    for path in ("/api/auth/me", "/api/tickets", "/api/dashboard"):
        resp = w.call("GET", path, actor=kept)
        expect(resp.status == 401, f"old session after reactivation: GET {path} -> {resp.status}, expected 401")
    expect(w.login(other).status == 200, "a new login after reactivation fails")


def sec_07(w: World) -> None:
    alice, bob = w.a("alice"), w.a("bob")
    before = w.total(alice, "/api/tickets")
    problems: list[str] = []
    for label, token in (("no X-CSRF-Token", None), ("an invalid token", "x" * 43),
                         ("the token of another session", bob.csrf)):
        resp = w.call("POST", "/api/tickets", {"title": "Sans jeton CSRF", "description": "Mutation sans le bon "
                      "jeton CSRF.", "client_request_id": str(uuid.uuid4())}, actor=alice, csrf=token)
        if resp.status != 403:
            problems.append(f"mutation with {label} -> {resp.status}")
    out = w.call("POST", "/api/auth/logout", actor=alice, csrf=None)
    if out.status != 403:
        problems.append(f"logout without CSRF on a valid session -> {out.status}")
    if w.call("GET", "/api/auth/me", actor=alice).status != 200:
        problems.append("a logout refused for CSRF revoked the session")
        w.must_login(alice)
    for label, origin in (("absent", None), ("null", "null"), ("foreign", "http://evil.example")):
        login = w.login(alice.fresh(), origin=origin)
        if login.status != 403:
            problems.append(f"login with {label} Origin -> {login.status}")
        resp = w.call("POST", "/api/tickets", {"title": "Origine refusée", "description": "Mutation depuis une "
                      "origine refusée.", "client_request_id": str(uuid.uuid4())}, actor=alice, origin=origin)
        if resp.status != 403:
            problems.append(f"mutation with {label} Origin -> {resp.status}")
    if w.total(alice, "/api/tickets") != before:
        problems.append("a refused mutation created a ticket")
    anonymous = w.call("POST", "/api/tickets", {"title": "Anonyme", "description": "Mutation anonyme sans "
                       "session.", "client_request_id": str(uuid.uuid4())})
    if anonymous.status != 401:
        problems.append(f"anonymous mutation without CSRF -> {anonymous.status}, expected 401")
    evil = "http://evil.example"
    for resp in (w.call("OPTIONS", "/api/tickets", origin=evil,
                        headers={"Access-Control-Request-Method": "POST",
                                 "Access-Control-Request-Headers": "content-type,x-csrf-token"}),
                 w.call("GET", "/api/tickets", actor=alice, origin=evil)):
        allow = resp.header("Access-Control-Allow-Origin")
        if resp.header("Access-Control-Allow-Credentials").lower() == "true" and allow in ("*", evil):
            problems.append(f"CORS allows {allow!r} with credentials")
    legit = w.post_ticket(alice)
    if legit.status != 201:
        problems.append(f"legitimate mutation -> {legit.status}")
    _problems(problems)


def sec_08(w: World) -> None:
    alice, camille, admin = w.a("alice"), w.a("camille"), w.admin
    target = w.add_user("sec08", "client")
    tid = w.ticket(alice, title="Ticket SEC-08 original")
    new_user = {"email": "sec08-new@relais.test", "display_name": "Nouveau", "password": "Phrase de passe neuve 26",
                "role": "client"}
    bodies = {"/api/auth/logout": _UNSET, "/api/users": new_user, f"/api/users/{target.id}": {"active": False},
              "/api/tickets": {"title": "Ticket anonyme", "description": "Ticket créé sans aucune session.",
                               "client_request_id": str(uuid.uuid4())},
              f"/api/tickets/{tid}": {"expected_version": 1, "priority": "high"},
              f"/api/tickets/{tid}/messages": {"body": "Anonyme", "visibility": "public",
                                               "client_request_id": str(uuid.uuid4())}}
    problems: list[str] = []
    for method, template in SPEC_ROUTES:
        if template in ("/api/auth/login", "/api/auth/logout"):
            continue
        path = template.replace("{}", target.id if "/users/" in template else tid, 1)
        resp = w.call(method, path, bodies.get(path, _UNSET) if method != "GET" else _UNSET)
        if resp.status != 401:
            problems.append(f"anonymous {method} {template} -> {resp.status}")
    admin_only = [("GET", "/api/users", _UNSET), ("POST", "/api/users", new_user),
                  ("PATCH", f"/api/users/{target.id}", {"active": False})]
    for actor, routes in ((alice, admin_only + [("GET", "/api/assignees", _UNSET)]), (camille, admin_only)):
        for method, path, body in routes:
            resp = w.call(method, path, body, actor=actor)
            if resp.status != 403:
                problems.append(f"{actor.role} {method} {path.replace(target.id, '{id}')} -> {resp.status}")
    for actor, path in ((camille, "/api/assignees"), (admin, "/api/assignees"), (admin, "/api/users")):
        resp = w.call("GET", path, actor=actor)
        if resp.status != 200:
            problems.append(f"{actor.role} GET {path} -> {resp.status}")
    resp = w.patch(alice, tid, version=1, priority="high")
    if resp.status != 403:
        problems.append(f"client PATCH of its own ticket -> {resp.status}")
    for method, body in (("PUT", {"title": "Remplacé par PUT", "description": "Description remplacée par PUT."}),
                         ("DELETE", _UNSET)):
        resp = w.call(method, f"/api/tickets/{tid}", body, actor=admin)
        if 200 <= resp.status < 300:
            problems.append(f"{method} /api/tickets/{{id}} -> {resp.status}")
    resp = w.call("DELETE", f"/api/users/{target.id}", actor=admin)
    if 200 <= resp.status < 300:
        problems.append(f"DELETE /api/users/{{id}} -> {resp.status}")
    after = w.call("GET", f"/api/tickets/{tid}", actor=alice)
    if after.status != 200 or after.item("title") != "Ticket SEC-08 original":
        problems.append(f"ticket changed by a refused request: {after}")
    users = {str(u.get("id")): u for u in w.items(admin, "/api/users")}
    if users.get(target.id, {}).get("active") is not True:
        problems.append("a refused request deactivated or deleted an account")
    _problems(problems)


def _same_404(a: Resp, b: Resp, ids: tuple[str, str]) -> bool:
    def norm(resp: Resp) -> tuple:
        message = str(resp.error.get("message", ""))
        for value in ids:
            message = message.replace(value, "<id>")
        return resp.status, resp.code, message
    return norm(a) == norm(b)


def sec_09(w: World) -> None:
    alice, bob = w.a("alice"), w.a("bob")
    key = str(uuid.uuid4())
    title = "Ticket privé de Bob neuf"
    description = "Description privée que seule l'équipe et Bob peuvent lire."
    tb = w.ticket(bob, title=title, description=description, key=key)
    missing = str(uuid.uuid4())
    problems: list[str] = []
    calls = [("GET", "", _UNSET), ("PATCH", "", {"expected_version": 1, "priority": "high"}),
             ("GET", "/messages", _UNSET),
             ("POST", "/messages", {"body": "Intrusion", "visibility": "public", "client_request_id": str(uuid.uuid4())}),
             ("GET", "/history", _UNSET)]
    for method, suffix, body in calls:
        other = w.call(method, f"/api/tickets/{tb}{suffix}", body, actor=alice)
        absent = w.call(method, f"/api/tickets/{missing}{suffix}", body, actor=alice)
        if other.status != 404 or absent.status != 404:
            problems.append(f"{method} {suffix or '/'} on another client's ticket -> {other.status} "
                            f"(missing id -> {absent.status}), expected 404 for both")
        elif not _same_404(other, absent, (tb, missing)):
            problems.append(f"{method} {suffix or '/'}: 404 differs from a missing id ({other.text[:80]} vs "
                            f"{absent.text[:80]})")
    owner_view = w.get(tb, bob)
    if owner_view.get("version") != 1 or owner_view.get("priority") != "normal":
        problems.append(f"refused requests changed Bob's ticket: {owner_view}")
    if w.total(bob, f"/api/tickets/{tb}/messages") != 0:
        problems.append("a refused request added a message")
    if tb in w.ids(alice, "/api/tickets"):
        problems.append("Bob's ticket is in Alice's list")
    if w.total(alice, "/api/tickets", q="privé de Bob") != 0:
        problems.append("Alice finds Bob's ticket by search")
    dash = w.call("GET", "/api/dashboard", actor=alice)
    if dash.item("total") != w.total(alice, "/api/tickets"):
        problems.append(f"Alice's dashboard total {dash.item('total')} is not her own ticket count")
    reuse = w.post_ticket(alice, title=title, description=description, key=key)
    if reuse.status != 201 or str(reuse.item("id")) == tb or str(reuse.item("owner_id")) != alice.id:
        problems.append(f"Alice reusing Bob's client_request_id -> {reuse}, expected her own new ticket (201)")
    _problems(problems)


def sec_10(w: World) -> None:
    alice, camille = w.a("alice"), w.a("camille")
    mixed = w.ticket(alice, title="Ticket mixte public et interne")
    replies = [w.message(camille, mixed, "Réponse publique visible par le client"),
               w.message(camille, mixed, f"{SECRET} contenu de la note", "internal"),
               w.message(alice, mixed, "Merci pour cette réponse")]
    expect([r.status for r in replies] == [201, 201, 201], f"messages -> {[r.status for r in replies]}")
    note_id = str(replies[1].item("id"))
    only = w.ticket(alice, title="Ticket avec seulement une note interne")
    note2 = w.message(camille, only, f"{SECRET} seule note du ticket", "internal")
    expect(note2.status == 201, f"internal note -> {note2}")
    problems: list[str] = []
    if w.total(camille, f"/api/tickets/{mixed}/messages") != 3:
        problems.append("the staff does not see the 3 messages")
    seen = w.items(alice, f"/api/tickets/{mixed}/messages")
    if len(seen) != 2 or w.total(alice, f"/api/tickets/{mixed}/messages") != 2:
        problems.append(f"the client sees {len(seen)} messages, expected the 2 public ones")
    first_page = w.page(alice, f"/api/tickets/{mixed}/messages", page=1, page_size=1)
    if first_page.body["total"] != 2:
        problems.append(f"paginated total for the client {first_page.body['total']}, expected 2")
    if w.total(alice, f"/api/tickets/{only}/messages") != 0:
        problems.append("the client sees messages on a ticket that only has internal notes")
    leaks = []
    for tid in (mixed, only):
        for path in (f"/api/tickets/{tid}", f"/api/tickets/{tid}/messages?page_size=50",
                     f"/api/tickets/{tid}/history?page_size=50"):
            text = w.call("GET", path, actor=alice).text
            if SECRET in text or note_id in text or str(note2.item("id")) in text:
                leaks.append(path.split("?")[0].replace(tid, "{id}"))
    for path in ("/api/tickets?page_size=50", "/api/dashboard", f"/api/tickets?q={SECRET}"):
        if SECRET in w.call("GET", path, actor=alice).text:
            leaks.append(path)
    if leaks:
        problems.append(f"internal content or ids visible to the client in {sorted(set(leaks))}")
    if w.total(alice, f"/api/tickets/{mixed}/history") >= w.history_total(mixed):
        problems.append("the client sees as many history events as the staff")
    _problems(problems)


def sec_11(w: World) -> None:
    alice, bob, camille, admin = w.a("alice"), w.a("bob"), w.a("camille"), w.admin
    before = w.total(alice, "/api/tickets")
    problems: list[str] = []
    for extra in ({"owner_id": bob.id}, {"status": "closed"}, {"version": 7}, {"priority": "high"},
                  {"assignee_id": camille.id}, {"created_at": "2020-01-01T00:00:00+00:00"}, {"foo": "bar"}):
        resp = w.post_ticket(alice, extra=extra)
        if resp.status != 422:
            problems.append(f"ticket creation with {list(extra)[0]} -> {resp.status}")
    if w.total(alice, "/api/tickets") != before:
        problems.append("a refused creation left a ticket")
    tid = w.ticket(alice)
    internal = w.message(alice, tid, "Le client tente une note interne", "internal")
    if internal.status != 403:
        problems.append(f"client internal note -> {internal.status}, expected 403")
    for extra in ({"author_id": camille.id}, {"created_at": "2020-01-01T00:00:00+00:00"}, {"foo": 1}):
        resp = w.message(alice, tid, "Message avec champ interdit", extra=extra)
        if resp.status != 422:
            problems.append(f"message with {list(extra)[0]} -> {resp.status}")
    for body in ({"role": "admin"}, {"email": "autre@relais.test"}, {"active": True, "role": "admin"}):
        resp = w.call("PATCH", f"/api/users/{alice.id}", body, actor=admin)
        if resp.status != 422:
            problems.append(f"PATCH user {sorted(body)} -> {resp.status}")
    me = w.call("GET", "/api/auth/me", actor=alice)
    if find_key(me.body, "role") != "client":
        problems.append(f"Alice's role became {find_key(me.body, 'role')!r}")
    for fields in ({"title": "Titre modifié"}, {"owner_id": bob.id}, {"foo": 1}):
        resp = w.patch(camille, tid, **fields)
        if resp.status != 422:
            problems.append(f"ticket PATCH with {list(fields)[0]} -> {resp.status}")
    resp = w.create_user("sec11@relais.test", "Champ inconnu", "Phrase de passe sec11 2026", "client",
                         extra={"is_superuser": True})
    if resp.status != 422:
        problems.append(f"account creation with an unknown field -> {resp.status}")
    _problems(problems)


def sec_12(w: World) -> None:
    alice, camille = w.a("alice"), w.a("camille")
    title = "<script>alert('titre')</script> Écran"
    description = "<img src=x onerror=alert(1)> l'apostrophe reste littérale ; DROP TABLE tickets; --"
    tid = w.ticket(alice, title=title, description=description)
    problems: list[str] = []
    got = w.get(tid, alice)
    if got.get("title") != title or got.get("description") != description:
        problems.append("title or description not returned literally")
    texts = {"public": "<img src=x onerror=alert(2)> d'accord", "internal": "<script>alert(3)</script> note"}
    for visibility, text in texts.items():
        resp = w.message(camille, tid, text, visibility)
        if resp.status != 201 or resp.item("body") != text:
            problems.append(f"{visibility} message not stored literally: {resp}")
    bodies = [m.get("body") for m in w.items(camille, f"/api/tickets/{tid}/messages")]
    if sorted(bodies) != sorted(texts.values()):
        problems.append(f"messages read back differently: {bodies}")
    name = "<b>O'Brien</b> & co"
    user = w.create_user("sec12@relais.test", name, "Phrase de passe sec12 2026", "agent")
    if user.status != 201 or user.item("display_name") != name:
        problems.append(f"display name not stored literally: {user}")
    injected = w.call("GET", "/api/tickets", actor=alice, params={"q": "' OR '1'='1"})
    if injected.status != 200 or injected.item("total") != 0:
        problems.append(f"search \"' OR '1'='1\" -> {injected.status} total={injected.item('total')}, expected 0")
    found = w.ids(alice, "/api/tickets", q="l'apostrophe reste")
    if tid not in found:
        problems.append("search with an apostrophe does not find the literal text")
    _problems(problems)


def sec_13(w: World) -> None:
    admin, emma = w.admin, w.a("emma")
    for user in w.items(admin, "/api/users"):
        if user.get("role") == "admin" and user.get("active") and str(user.get("id")) not in (admin.id, emma.id):
            w.set_active(str(user["id"]), False)
    expect(w.set_active(emma.id, False).status == 200, "deactivate the second admin")
    last = w.set_active(admin.id, False, actor=admin)
    expect(last.status == 409, f"deactivating the last active admin -> {last.status}, expected 409")
    expect(w.call("GET", "/api/auth/me", actor=admin).status == 200, "the last admin lost its session")
    expect(w.set_active(emma.id, True).status == 200, "reactivate the second admin")
    w.must_login(emma)
    rounds = [("each other", lambda: w.set_active(emma.id, False, admin), lambda: w.set_active(admin.id, False, emma)),
              ("each other", lambda: w.set_active(emma.id, False, admin), lambda: w.set_active(admin.id, False, emma)),
              ("themselves", lambda: w.set_active(admin.id, False, admin), lambda: w.set_active(emma.id, False, emma))]
    for label, one, two in rounds:
        statuses = [r.status for r in w.concurrently([one, two])]
        alive = [a for a in (admin, emma) if w.call("GET", "/api/auth/me", actor=a).status == 200]
        expect(alive, f"two admins deactivating {label} at once -> {statuses}: no active admin left")
        survivor = alive[0]
        for other in (admin, emma):
            if other not in alive:
                expect(w.set_active(other.id, True, survivor).status == 200, "reactivate after the race")
                w.must_login(other)


def sec_14(w: World) -> None:
    alice, bob, camille, admin = w.a("alice"), w.a("bob"), w.a("camille"), w.admin
    problems: list[str] = []
    for body in ({"role": "admin"}, {"email": "camille-bis@relais.test"}):
        resp = w.call("PATCH", f"/api/users/{camille.id}", body, actor=admin)
        if resp.status != 422:
            problems.append(f"PATCH {list(body)[0]} -> {resp.status}")
    me = w.call("GET", "/api/auth/me", actor=camille)
    if find_key(me.body, "role") != "agent" or find_key(me.body, "email") != camille.email:
        problems.append(f"role or email changed: {me}")
    created = w.call("POST", "/api/users", {"email": "par-agent@relais.test", "display_name": "Par agent",
                     "password": "Phrase de passe agent 2026", "role": "client"}, actor=camille)
    if created.status != 403:
        problems.append(f"agent creates an account -> {created.status}")
    if w.call("GET", "/api/assignees", actor=alice).status != 403:
        problems.append("a client reads the assignee directory")
    first = w.page(camille, "/api/assignees")
    if not {"items", "total", "page", "page_size"} <= set(first.body):
        problems.append("the directory is not paginated")
    directory = w.items(camille, "/api/assignees")
    ids = {str(i.get("id")) for i in directory}
    if not {camille.id, admin.id} <= ids:
        problems.append("active agent or admin missing from the directory")
    if {alice.id, bob.id} & ids:
        problems.append("clients listed in the directory")
    keys = sorted({k for item in directory for k in _no_secret_keys(item)})
    if keys:
        problems.append(f"directory exposes {keys}")
    text = w.call("GET", "/api/assignees", actor=camille, params={"page_size": 50}).text
    if alice.email in text or bob.email in text:
        problems.append("client emails in the directory")
    ghost = w.add_user("sec14", "agent")
    tid = w.ticket(alice)
    reply = w.message(ghost, tid, "Réponse d'un agent bientôt désactivé")
    expect(w.set_active(ghost.id, False).status == 200, "deactivate sec14")
    if ghost.id in w.ids(camille, "/api/assignees"):
        problems.append("a deactivated agent stays in the directory")
    users = {str(u.get("id")): u for u in w.items(admin, "/api/users")}
    if users.get(ghost.id, {}).get("active") is not False:
        problems.append("a deactivated account is no longer listed as inactive")
    if str(reply.item("id")) not in w.ids(camille, f"/api/tickets/{tid}/messages"):
        problems.append("the deactivated agent's message disappeared")
    _problems(problems)


def sec_15(w: World) -> None:
    alice, admin = w.a("alice"), w.admin
    tid = w.ticket(alice)
    login = w.login(alice.fresh())
    private = {"login": login, "auth/me": w.call("GET", "/api/auth/me", actor=alice),
               "tickets": w.call("GET", "/api/tickets", actor=alice),
               "ticket": w.call("GET", f"/api/tickets/{tid}", actor=alice),
               "messages": w.call("GET", f"/api/tickets/{tid}/messages", actor=alice),
               "dashboard": w.call("GET", "/api/dashboard", actor=alice),
               "users": w.call("GET", "/api/users", actor=admin)}
    missing = [name for name, r in private.items() if "no-store" not in r.header("Cache-Control").lower()]
    problems = [f"no Cache-Control: no-store on {missing}"] if missing else []
    root = str(w.product.dir)
    leaks = sorted({f"{m} {p.split('?')[0]} -> {r.status}" for m, p, r in w.api.errors
                    if _LEAK.search(r.text) or root in r.text})
    if leaks:
        problems.append(f"stack trace, SQL or private path in error bodies: {leaks[:3]}")
    _problems(problems)


# --------------------------------------------------------------------------- FUN


def fun_01(w: World) -> None:
    alice, camille, admin = w.a("alice"), w.a("camille"), w.admin
    resp = w.post_ticket(alice)
    expect(resp.status == 201, f"client creation -> {resp}")
    body = resp.body
    expect(str(body.get("owner_id")) == alice.id and body.get("status") == "open" and body.get("priority") == "normal"
           and body.get("assignee_id") is None and body.get("version") == 1,
           f"new ticket {body}, expected owner=session, open, normal, unassigned, version 1")
    problems: list[str] = []
    for actor in (camille, admin):
        refused = w.post_ticket(actor)
        if refused.status != 403:
            problems.append(f"{actor.role} creates a ticket -> {refused.status}, expected 403")
    for title, expected in (("x" * 4, 422), ("t" * 5, 201), ("T" * 120, 201), ("T" * 121, 422),
                            ("   abcd   ", 422), (" " * 10, 422), ("\n\t  \n", 422)):
        got = w.post_ticket(alice, title=title)
        if got.status != expected:
            problems.append(f"title {title!r:.20} ({len(title)}) -> {got.status}, expected {expected}")
    for desc, expected in (("d" * 19, 422), ("d" * 20, 201), ("d" * 5000, 201), ("d" * 5001, 422),
                           (" " * 30, 422), ("  " + "d" * 19 + "  ", 422)):
        got = w.post_ticket(alice, description=desc)
        if got.status != expected:
            problems.append(f"description of {len(desc)} characters ({len(desc.strip())} trimmed) -> "
                            f"{got.status}, expected {expected}")
    multiline = "Première ligne du problème\nDeuxième ligne\n\nFin du message."
    tid = w.ticket(alice, description=multiline)
    if w.get(tid, alice).get("description") != multiline:
        problems.append("line breaks of the description are not kept")
    _problems(problems)


def fun_02(w: World) -> None:
    problems: list[str] = []
    for name in ("alice", "bob"):
        client = w.a(name)
        items = w.items(client, "/api/tickets")
        ids = {str(i.get("id")) for i in items}
        if ids != w.tickets[client.email]:
            problems.append(f"{name} sees {len(ids)} tickets, created {len(w.tickets[client.email])}")
        if any(str(i.get("owner_id")) != client.id for i in items):
            problems.append(f"{name}'s list holds tickets of other owners")
        if w.total(client, "/api/tickets") != len(w.tickets[client.email]):
            problems.append(f"{name}'s total disagrees with the tickets created")
    everything = set().union(*w.tickets.values())
    for name in ("camille", "admin"):
        ids = w.ids(w.actors[name], "/api/tickets")
        if ids != everything:
            problems.append(f"{name} sees {len(ids)} tickets, {len(everything)} exist")
    missing = str(uuid.uuid4())
    for name in ("alice", "camille"):
        status = w.call("GET", f"/api/tickets/{missing}", actor=w.actors[name]).status
        if status != 404:
            problems.append(f"{name} GET of a missing ticket -> {status}")
    _problems(problems)


def fun_03(w: World) -> None:
    alice, camille, dylan, emma = w.a("alice"), w.a("camille"), w.a("dylan"), w.a("emma")
    tid = w.ticket(alice)
    problems: list[str] = []
    if w.patch(alice, tid, priority="high").status != 403:
        problems.append("a client changes the priority")
    if w.patch(camille, tid, priority="urgent").status != 422:
        problems.append("priority 'urgent' accepted")
    changed = w.patch(camille, tid, priority="high")
    expect(changed.status == 200 and changed.item("priority") == "high", f"priority change -> {changed}")
    version = w.version(tid)
    ghost = w.add_user("fun03", "agent")
    expect(w.set_active(ghost.id, False).status == 200, "deactivate fun03")
    for label, target in (("a client", alice.id), ("an inactive agent", ghost.id), ("an unknown id", str(uuid.uuid4()))):
        resp = w.patch(camille, tid, assignee_id=target)
        if resp.status not in (400, 404, 409, 422):
            problems.append(f"assignment to {label} -> {resp.status}")
        if w.version(tid) != version:
            problems.append(f"refused assignment to {label} wrote the ticket")
    for label, target in (("an agent", dylan.id), ("an admin", emma.id), ("null", None)):
        resp = w.patch(camille, tid, assignee_id=target)
        if resp.status != 200 or resp.item("assignee_id") != target:
            problems.append(f"assignment to {label} -> {resp}")
    closed = w.ticket(alice)
    w.drive(closed, "closed")
    for label, target in (("an agent", dylan.id), ("null", None)):
        resp = w.patch(camille, closed, assignee_id=target)
        if resp.status != 409:
            problems.append(f"assignment change ({label}) on a closed ticket -> {resp.status}, expected 409")
    if w.patch(camille, closed, priority="low").status != 200:
        problems.append("priority change on a closed ticket refused")
    resolved = w.ticket(alice)
    w.drive(resolved, "resolved")
    resp = w.patch(camille, resolved, status="closed", assignee_id=dylan.id)
    if resp.status != 409 or w.get(resolved).get("status") != "resolved":
        problems.append(f"closing with an assignment change -> {resp.status}, expected 409 without write")
    _problems(problems)


def fun_04(w: World) -> None:
    alice, camille = w.a("alice"), w.a("camille")
    problems: list[str] = []

    def move(tid: str, target: str, expected: int, label: str) -> None:
        before = w.get(tid)
        resp = w.patch(camille, tid, version=before.get("version"), status=target)
        after = w.get(tid)
        if resp.status != expected:
            problems.append(f"{label}: {before.get('status')} -> {target} gave {resp.status}, expected {expected}")
        elif expected == 409 and (after.get("version") != before.get("version") or after.get("status") != before.get("status")):
            problems.append(f"{label}: refused but the ticket changed")
        elif expected == 200 and after.get("status") != target:
            problems.append(f"{label}: status is {after.get('status')}")
        elif expected == 200 and target == before.get("status") and after.get("version") != before.get("version"):
            problems.append(f"{label}: a no-op changed the version")

    tid = w.ticket(alice)
    move(tid, "in_progress", 409, "unassigned")
    expect(w.patch(camille, tid, assignee_id=camille.id).status == 200, "assign")
    move(tid, "in_progress", 200, "effective open->in_progress")
    move(tid, "resolved", 409, "no reply at all")
    expect(w.message(camille, tid, "Note interne seulement", "internal").status == 201, "internal note")
    move(tid, "resolved", 409, "only an internal note")
    expect(w.message(alice, tid, "Message du client seulement").status == 201, "client message")
    move(tid, "resolved", 409, "only a client message")
    move(tid, "open", 200, "effective in_progress->open")
    move(tid, "in_progress", 200, "back to in_progress")
    expect(w.message(camille, tid, "Réponse publique de l'équipe").status == 201, "public staff reply")
    move(tid, "resolved", 200, "effective in_progress->resolved")
    expect(w.patch(camille, tid, assignee_id=None).status == 200, "unassign a resolved ticket")
    move(tid, "in_progress", 409, "reopen without assignee")
    expect(w.patch(camille, tid, assignee_id=camille.id).status == 200, "reassign")
    move(tid, "in_progress", 200, "effective resolved->in_progress")
    move(tid, "resolved", 200, "resolve again")
    move(tid, "closed", 200, "effective resolved->closed")
    opened, working, solved = w.ticket(alice), w.ticket(alice), w.ticket(alice)
    w.drive(working, "in_progress")
    w.drive(solved, "resolved")
    for ticket_id, status in ((opened, "open"), (working, "in_progress"), (solved, "resolved"), (tid, "closed")):
        move(ticket_id, status, 200, f"identity {status}")
    for ticket_id, target in ((opened, "resolved"), (opened, "closed"), (working, "closed"), (solved, "open"),
                              (tid, "open"), (tid, "in_progress"), (tid, "resolved")):
        move(ticket_id, target, 409, "forbidden")
    _problems(problems)


def fun_05(w: World) -> None:
    alice, bob, camille, dylan = w.a("alice"), w.a("bob"), w.a("camille"), w.a("dylan")
    tid = w.ticket(alice)
    problems: list[str] = []
    own = w.message(alice, tid, "Bonjour, avez-vous des nouvelles ?")
    expect(own.status == 201, f"client message -> {own}")
    stamp = _parse_dt(own.item("created_at"))
    if str(own.item("author_id")) != alice.id or own.item("visibility") != "public":
        problems.append(f"client message author/visibility: {own.body}")
    if stamp is None or abs(stamp - datetime.now(timezone.utc)) > timedelta(hours=1):
        problems.append(f"message created_at {own.item('created_at')!r} is not a server UTC date")
    for actor, visibility in ((dylan, "public"), (camille, "internal")):
        resp = w.message(actor, tid, "Réponse de l'équipe", visibility)
        if resp.status != 201:
            problems.append(f"{actor.email} {visibility} message on an unassigned ticket -> {resp.status}")
    if w.message(alice, tid, "Note interne du client", "internal").status != 403:
        problems.append("a client posts an internal note")
    if w.message(bob, tid, "Message sur le ticket d'autrui").status != 404:
        problems.append("a client posts on another client's ticket")
    if w.get(tid).get("status") != "open":
        problems.append("a message changed the status")
    for body, expected in (("", 422), ("   \n ", 422), ("a", 201), ("b" * 5000, 201), ("c" * 5001, 422)):
        resp = w.message(alice, tid, body)
        if resp.status != expected:
            problems.append(f"message of {len(body)} characters ({len(body.strip())} trimmed) -> {resp.status}, "
                            f"expected {expected}")
    public = w.total(alice, f"/api/tickets/{tid}/messages")
    if public != w.total(camille, f"/api/tickets/{tid}/messages") - 1:
        problems.append("the client does not see exactly the public messages")
    closed = w.ticket(alice)
    w.drive(closed, "closed")
    for actor, visibility in ((alice, "public"), (camille, "public"), (camille, "internal")):
        resp = w.message(actor, closed, "Après fermeture", visibility)
        if resp.status != 409:
            problems.append(f"{visibility} message on a closed ticket by {actor.role} -> {resp.status}, expected 409")
    _problems(problems)


def fun_06(w: World) -> None:
    alice, camille, dylan = w.a("alice"), w.a("camille"), w.a("dylan")
    problems: list[str] = []
    for round_ in range(3):
        tid = w.ticket(alice)
        version, events = w.version(tid), w.history_total(tid)
        answers = w.concurrently([lambda: w.patch(camille, tid, version=version, priority="high"),
                                  lambda: w.patch(dylan, tid, version=version, priority="low")])
        statuses = sorted(r.status for r in answers)
        if statuses != [200, 409]:
            problems.append(f"round {round_}: two PATCH of one version -> {statuses}, expected [200, 409]")
        elif next(r for r in answers if r.status == 409).code != "VERSION_CONFLICT":
            problems.append(f"round {round_}: conflict code {next(r for r in answers if r.status == 409).code!r}")
        if w.version(tid) != version + 1 or w.history_total(tid) != events + 1:
            problems.append(f"round {round_}: version or history moved by more than one mutation")
    for round_ in range(3):
        tid = w.ticket(alice)
        w.drive(tid, "resolved")
        version = w.version(tid)
        count = w.total(camille, f"/api/tickets/{tid}/messages")
        close, message = w.concurrently([lambda: w.patch(camille, tid, version=version, status="closed"),
                                         lambda: w.message(dylan, tid, f"Message en course {round_}")])
        after = w.get(tid)
        now = w.total(camille, f"/api/tickets/{tid}/messages")
        if (close.status == 200) + (message.status == 201) != 1:
            problems.append(f"close/message race {round_}: close {close.status}, message {message.status}, "
                            "expected exactly one success")
        elif close.status == 200 and (after.get("status") != "closed" or now != count):
            problems.append(f"close/message race {round_}: closing won but a message was written")
        elif message.status == 201 and (after.get("status") != "resolved" or now != count + 1):
            problems.append(f"close/message race {round_}: the message won but the ticket closed")
    _problems(problems)


def fun_07(w: World) -> None:
    alice, bob, camille = w.a("alice"), w.a("bob"), w.a("camille")
    problems: list[str] = []
    key = str(uuid.uuid4())
    title, description = "Idempotence sept", "Ticket créé une seule fois malgré les reprises."
    before = w.total(alice, "/api/tickets")
    first = w.post_ticket(alice, title=title, description=description, key=key)
    expect(first.status == 201, f"creation -> {first}")
    ticket_id = str(first.item("id"))
    again = w.post_ticket(alice, title=title, description=description, key=key)
    if again.status != 200 or str(again.item("id")) != ticket_id:
        problems.append(f"replay of the creation -> {again.status} id {again.item('id')}, expected 200 same id")
    other = w.post_ticket(alice, title=title + " modifié", description=description, key=key)
    if other.status != 409 or other.code != "IDEMPOTENCY_CONFLICT":
        problems.append(f"same key, other payload -> {other.status} {other.code}")
    if w.total(alice, "/api/tickets") != before + 1:
        problems.append("the replays created more than one ticket")
    for_bob = w.post_ticket(bob, title=title, description=description, key=key)
    if for_bob.status != 201 or str(for_bob.item("id")) == ticket_id:
        problems.append(f"another user with the same key -> {for_bob.status}, expected its own ticket")
    key2 = str(uuid.uuid4())
    before = w.total(alice, "/api/tickets")
    racing = w.concurrently([lambda: w.post_ticket(alice, title="Reprise simultanée", key=key2)] * 2)
    if {r.status for r in racing} - {200, 201} or len({str(r.item("id")) for r in racing}) != 1 \
            or w.total(alice, "/api/tickets") != before + 1:
        problems.append(f"simultaneous retries -> {[r.status for r in racing]}, expected one ticket, same id")
    tid, tid2 = w.ticket(alice), w.ticket(alice)
    mkey, text = str(uuid.uuid4()), "Message idempotent sept"
    m1 = w.message(alice, tid, text, key=mkey)
    expect(m1.status == 201, f"message -> {m1}")
    m2 = w.message(alice, tid, text, key=mkey)
    if m2.status != 200 or m2.item("id") != m1.item("id"):
        problems.append(f"message replay -> {m2.status}, expected 200 same id")
    for label, resp in (("other content", w.message(alice, tid, "Autre contenu", key=mkey)),
                        ("other ticket", w.message(alice, tid2, text, key=mkey))):
        if resp.status != 409 or resp.code != "IDEMPOTENCY_CONFLICT":
            problems.append(f"message key reused with {label} -> {resp.status} {resp.code}")
    ckey = str(uuid.uuid4())
    w.message(camille, tid, "Réponse sept", "public", key=ckey)
    flipped = w.message(camille, tid, "Réponse sept", "internal", key=ckey)
    if flipped.status != 409 or flipped.code != "IDEMPOTENCY_CONFLICT":
        problems.append(f"message key reused with other visibility -> {flipped.status} {flipped.code}")
    if w.message(bob, tid, text, key=mkey).status != 404:
        problems.append("rights are not checked before the replay")
    if [m.get("body") for m in w.items(camille, f"/api/tickets/{tid}/messages")].count(text) != 1:
        problems.append("the replays created more than one message")
    closing = w.ticket(alice)
    akey = str(uuid.uuid4())
    before_close = w.message(alice, closing, "Message avant la fermeture", key=akey)
    w.drive(closing, "closed")
    replay = w.message(alice, closing, "Message avant la fermeture", key=akey)
    if replay.status != 200 or replay.item("id") != before_close.item("id"):
        problems.append(f"replay of an existing message on a closed ticket -> {replay.status}, expected 200")
    if w.message(alice, closing, "Nouveau message après fermeture").status != 409:
        problems.append("a new key is accepted on a closed ticket")
    w.facts["replay_after_restart"] = {"ticket": (key, title, description, ticket_id),
                                       "message": (tid, mkey, text, m1.item("id"))}
    _problems(problems)


def fun_07_after_restart(w: World) -> None:
    replay = w.facts.get("replay_after_restart")
    expect(replay, "nothing recorded before the restart")
    key, title, description, ticket_id = replay["ticket"]
    resp = w.post_ticket(w.a("alice"), title=title, description=description, key=key)
    expect(resp.status == 200 and str(resp.item("id")) == ticket_id,
           f"after restart: ticket replay -> {resp.status}, expected 200 same id")
    tid, mkey, text, message_id = replay["message"]
    resp = w.message(w.a("alice"), tid, text, key=mkey)
    expect(resp.status == 200 and resp.item("id") == message_id,
           f"after restart: message replay -> {resp.status}, expected 200 same id")


def fun_09(w: World) -> None:
    alice, camille = w.a("alice"), w.a("camille")
    agent = w.add_user("fun09", "agent")
    session = agent.snapshot()
    working = w.ticket(alice, title="Ticket FUN-09 en cours")
    expect(w.patch(camille, working, assignee_id=agent.id).status == 200, "assign")
    expect(w.patch(camille, working, status="in_progress").status == 200, "in_progress")
    closed = w.ticket(alice)
    expect(w.patch(camille, closed, assignee_id=agent.id).status == 200, "assign")
    w.drive(closed, "closed")
    snap = {t: (w.version(t), w.history_total(t)) for t in (working, closed)}
    expect(w.set_active(agent.id, False).status == 200, "deactivate the assignee")
    problems: list[str] = []
    if w.call("GET", "/api/auth/me", actor=session).status != 401:
        problems.append("the deactivated agent keeps its session")
    for tid, status in ((working, "in_progress"), (closed, "closed")):
        after = w.get(tid)
        version, events = snap[tid]
        if after.get("assignee_id") is not None:
            problems.append(f"{status} ticket still assigned to the deactivated agent")
        if after.get("status") != status:
            problems.append(f"{status} ticket became {after.get('status')}")
        if after.get("version") == version or w.history_total(tid) <= events:
            problems.append(f"{status} ticket unassigned without a new version and history event")
    if working not in w.ids(camille, "/api/tickets", unassigned="true", q="FUN-09 en cours"):
        problems.append("the unassigned in_progress ticket is not in the unassigned filter")
    expect(w.set_active(agent.id, True).status == 200, "reactivate")
    if w.get(working).get("assignee_id") is not None:
        problems.append("reactivation reassigned a ticket")
    if w.call("GET", "/api/auth/me", actor=session).status != 401:
        problems.append("reactivation revived the old session")
    if w.login(agent.fresh()).status != 200:
        problems.append("new login after reactivation fails")
    for round_ in range(3):
        racer = w.add_user(f"fun09-race{round_}", "agent")
        tid = w.ticket(alice)
        version = w.version(tid)
        statuses = [r.status for r in w.concurrently([
            lambda: w.patch(camille, tid, version=version, assignee_id=racer.id),
            lambda: w.set_active(racer.id, False)])]
        if str(w.get(tid).get("assignee_id")) == racer.id:
            problems.append(f"race {round_}: ticket assigned to a deactivated agent ({statuses})")
    _problems(problems)


def fun_10(w: World) -> None:
    client, alice, camille = w.add_user("fun10", "client"), w.a("alice"), w.a("camille")
    t1 = w.ticket(client, title="Imprimante Zorglub bloquée", description="Le bac ne se ferme plus depuis lundi matin.")
    t2 = w.ticket(client, title="Écran qui clignote", description="Le modèle ZORGLUB 3000 clignote depuis hier soir.")
    t3 = w.ticket(client, title="Symboles littéraux",
                  description="Taux à 100% et fichier nom_de_fichier.txt pour l'imprimante.")
    t4 = w.ticket(client, title="Problème unicode", description="Le mot Éléphant apparaît ici, une seule fois.")
    expect(w.message(camille, t1, "Pamplemousse dans un message public").status == 201, "public message")
    expect(w.message(camille, t4, "Kiwi dans une note interne", "internal").status == 201, "internal note")
    problems: list[str] = []
    for q, expected in (("zorglub", {t1, t2}), ("ZORGLUB", {t1, t2}), ("Éléphant", {t4}), ("100%", {t3}),
                        ("%", {t3}), ("_", {t3}), ("l'imprimante", {t3}), ("Pamplemousse", set()), ("Kiwi", set()),
                        ("", {t1, t2, t3, t4})):
        got = w.ids(client, "/api/tickets", q=q)
        if got != expected:
            problems.append(f"q={q!r} -> {len(got)} tickets, expected {len(expected)}")
    for size, expected in ((100, 200), (101, 422)):
        status = w.call("GET", "/api/tickets", actor=client, params={"q": "a" * size}).status
        if status != expected:
            problems.append(f"q of {size} characters -> {status}, expected {expected}")
    if w.ids(alice, "/api/tickets", q="zorglub"):
        problems.append("search returns tickets outside the client's scope")
    if not {t1, t2} <= w.ids(camille, "/api/tickets", q="zorglub"):
        problems.append("the staff does not find the tickets")
    page = w.page(client, "/api/tickets", q="zorglub", page_size=1)
    if page.body["total"] != 2 or len(page.body["items"]) != 1:
        problems.append(f"paginated search total={page.body['total']} items={len(page.body['items'])}")
    _problems(problems)


def fun_11(w: World) -> None:
    client, camille = w.add_user("fun11", "client"), w.a("camille")
    created = [w.ticket(client, title=f"Lot onze numéro {i:02d}",
                        description=f"Ticket de pagination numéro {i:02d} du lot onze.") for i in range(55)]
    problems: list[str] = []
    for params, expected in (({"page_size": 1}, 1), ({"page_size": 50}, 50), ({}, 20)):
        resp = w.page(client, "/api/tickets", **params)
        if len(resp.body["items"]) != expected or resp.body["total"] != 55:
            problems.append(f"{params or 'defaults'} -> {len(resp.body['items'])} items, total {resp.body['total']}")
    defaults = w.page(client, "/api/tickets").body
    if defaults.get("page") != 1 or defaults.get("page_size") != 20:
        problems.append(f"default page/page_size = {defaults.get('page')}/{defaults.get('page_size')}")
    for params in ({"page_size": 51}, {"page_size": 0}, {"page": 0}):
        status = w.call("GET", "/api/tickets", actor=client, params=params).status
        if status != 422:
            problems.append(f"{params} -> {status}, expected 422")
    beyond = w.page(client, "/api/tickets", page=100)
    if beyond.body["items"] or beyond.body["total"] != 55:
        problems.append("a page beyond the end is not empty with the full total")
    seen: list[dict] = []
    for number in range(1, 9):
        resp = w.page(client, "/api/tickets", page=number, page_size=7)
        if resp.body["total"] != 55:
            problems.append(f"page {number}: total {resp.body['total']}")
        seen += resp.body["items"]
    ids = [str(i.get("id")) for i in seen]
    if len(ids) != len(set(ids)) or set(ids) != set(created):
        problems.append(f"walking pages of 7: {len(ids)} items, {len(set(ids))} distinct, expected the 55")
    keys = [(_parse_dt(i.get("updated_at")), str(i.get("id"))) for i in seen]
    if any(k[0] is None for k in keys) or keys != sorted(keys, reverse=True):
        problems.append("not sorted by (updated_at DESC, id DESC)")
    for i in range(10):
        expect(w.patch(camille, created[i], priority="high" if i < 5 else "low").status == 200, "priority")
    for i in range(3):
        expect(w.patch(camille, created[i], assignee_id=camille.id).status == 200, "assign")
    for i in range(2):
        expect(w.patch(camille, created[i], status="in_progress").status == 200, "in_progress")
    for params, expected in (({"priority": "high"}, 5), ({"priority": "high", "assigned_to_me": "true"}, 3),
                             ({"priority": "high", "status": "in_progress"}, 2), ({"unassigned": "true"}, 52),
                             ({"priority": "low", "unassigned": "true"}, 5),
                             ({"status": "open", "priority": "normal"}, 45)):
        got = w.total(camille, "/api/tickets", q="Lot onze", **params)
        if got != expected:
            problems.append(f"filters {params} -> total {got}, expected {expected}")
    both = w.call("GET", "/api/tickets", actor=camille, params={"assigned_to_me": "true", "unassigned": "true"})
    if both.status != 422:
        problems.append(f"assigned_to_me and unassigned together -> {both.status}, expected 422")
    if w.call("GET", "/api/tickets", actor=camille, params={"status": "bogus"}).status != 422:
        problems.append("an unknown status filter is accepted")
    staff_filter = w.call("GET", "/api/tickets", actor=client, params={"assigned_to_me": "true"})
    if staff_filter.status not in (403, 422):
        problems.append(f"a client uses the staff-only filter -> {staff_filter.status}")
    _problems(problems)


def _dashboard(w: World, actor: Actor) -> dict:
    resp = w.call("GET", "/api/dashboard", actor=actor)
    by_status = resp.item("by_status")
    expect(resp.status == 200 and isinstance(resp.item("total"), int) and isinstance(by_status, dict)
           and all(isinstance(by_status.get(s), int) for s in STATUSES),
           f"GET /api/dashboard -> {resp}, expected {{total, by_status: {{open, in_progress, resolved, closed}}}}")
    return resp.body


def fun_12(w: World) -> None:
    client, camille, alice = w.add_user("fun12", "client"), w.a("camille"), w.a("alice")
    problems: list[str] = []
    empty = _dashboard(w, client)
    if empty["total"] != 0 or any(empty["by_status"][s] for s in STATUSES):
        problems.append(f"new client dashboard {empty}, expected zeros")
    first, second = w.ticket(client), w.ticket(client)
    w.drive(second, "in_progress")
    mine = _dashboard(w, client)
    if mine["total"] != 2 or [mine["by_status"][s] for s in STATUSES] != [1, 1, 0, 0]:
        problems.append(f"client dashboard {mine}, expected total 2, open 1, in_progress 1")
    staff = _dashboard(w, camille)
    if staff["total"] != w.total(camille, "/api/tickets") or sum(staff["by_status"].values()) != staff["total"]:
        problems.append("staff dashboard total disagrees with the list or the statuses")
    for status in STATUSES:
        if staff["by_status"][status] != w.total(camille, "/api/tickets", status=status):
            problems.append(f"staff by_status.{status} disagrees with the filtered list")
    w.drive(first, "in_progress")
    if _dashboard(w, camille)["by_status"]["in_progress"] != staff["by_status"]["in_progress"] + 1:
        problems.append("the dashboard does not follow a mutation")
    if _dashboard(w, alice)["total"] != w.total(alice, "/api/tickets"):
        problems.append("a client dashboard counts tickets outside its scope")
    _problems(problems)


def fun_13(w: World) -> None:
    alice, camille = w.a("alice"), w.a("camille")
    tid = w.ticket(alice)
    events = w.history_total(tid)
    problems: list[str] = []
    same = w.patch(camille, tid, version=1, priority="normal")
    if same.status != 200 or w.version(tid) != 1 or w.history_total(tid) != events:
        problems.append(f"identical PATCH -> {same.status}, version {w.version(tid)}: a no-op must change nothing")
    expect(w.patch(camille, tid, version=1, priority="high").status == 200, "effective PATCH")
    stale = w.patch(camille, tid, version=1, priority="high")
    if stale.status != 409 or stale.code != "VERSION_CONFLICT":
        problems.append(f"stale version on a no-op -> {stale.status} {stale.code}, expected 409 VERSION_CONFLICT")
    for label, body in (("no expected_version", {"priority": "low"}), ("no field", {"expected_version": 2})):
        status = w.call("PATCH", f"/api/tickets/{tid}", body, actor=camille).status
        if status != 422:
            problems.append(f"PATCH with {label} -> {status}, expected 422")
    for label, fields in (("forbidden transition", {"priority": "low", "status": "resolved"}),
                          ("client assignee", {"priority": "low", "assignee_id": alice.id})):
        resp = w.patch(camille, tid, version=2, **fields)
        after = w.get(tid)
        if resp.status < 400 or after.get("priority") != "high" or after.get("version") != 2:
            problems.append(f"multi-field PATCH with a {label} -> {resp.status}, partial write")
    expect(w.message(alice, tid, "Un message public").status == 201, "public message")
    if w.version(tid) != 3:
        problems.append("a public message did not add exactly one version")
    expect(w.message(camille, tid, "Une note interne", "internal").status == 201, "internal note")
    if w.version(tid) != 4:
        problems.append("an internal note did not add exactly one version")
    _problems(problems)


# --------------------------------------------------------------------------- ARC, UX, OPS


def arc_03(w: World) -> None:
    alice = w.a("alice")
    before = w.total(alice, "/api/tickets")
    key = str(uuid.uuid4())
    conn = sqlite3.connect(str(w.db), timeout=10, isolation_level=None)
    try:
        try:
            conn.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as exc:
            raise Fail(f"could not hold a lock on RELAIS_DB to simulate contention: {exc}") from exc
        started = time.monotonic()
        resp = w.post_ticket(alice, title="Ticket sous verrou", key=key, timeout=30)
        elapsed = time.monotonic() - started
    finally:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        conn.close()
    expect(resp.status == 503 and resp.code == "DB_BUSY",
           f"write while the database is locked -> {resp.status} {resp.code!r} after {elapsed:.1f} s, "
           "expected 503 DB_BUSY")
    expect(elapsed <= 9, f"DB_BUSY after {elapsed:.1f} s, the wait is capped at 5 s")
    expect(w.total(alice, "/api/tickets") == before, "the refused write left a ticket")
    again = w.post_ticket(alice, title="Ticket sous verrou", key=key)
    expect(again.status == 201, f"the same request once the lock is released -> {again.status}, expected 201")


def arc_06(w: World) -> None:
    errors = [(m, p, r) for m, p, r in w.api.errors if r.status in ERROR_STATUSES]
    expect(errors, "no error response observed")
    bad = sorted({f"{m} {p.split('?')[0]} -> {r.status}" for m, p, r in errors
                  if not (r.code and isinstance(r.error.get("message"), str) and r.error["message"].strip())})
    expect(not bad, f"{len(bad)} error responses without {{error: {{code, message}}}}: {bad[:4]}")
    doc = None
    for path in ("/openapi.json", "/api/openapi.json"):
        resp = w.call("GET", path)
        if resp.status == 200 and isinstance(resp.item("paths"), dict):
            doc = resp.body
            break
    expect(doc, "no OpenAPI document at /openapi.json or /api/openapi.json")
    paths = {re.sub(r"\{[^}]+\}", "{}", p): {m.upper() for m in ops} for p, ops in doc["paths"].items()
             if isinstance(ops, dict)}
    missing = [f"{m} {p}" for m, p in SPEC_ROUTES if m not in paths.get(p, set())]
    expect(not missing, f"OpenAPI misses {missing}")


def arc_07(w: World) -> None:
    alice, admin = w.a("alice"), w.admin
    tid = w.ticket(alice)
    expect(w.message(alice, tid, "Message pour les listes").status == 201, "message")
    problems: list[str] = []
    for template in ("/api/tickets", "/api/users", "/api/assignees", "/api/tickets/{}/messages",
                     "/api/tickets/{}/history"):
        path = template.replace("{}", tid)
        resp = w.call("GET", path, actor=admin)
        body = resp.body if isinstance(resp.body, dict) else {}
        if resp.status != 200 or not {"items", "total", "page", "page_size"} <= set(body):
            problems.append(f"{template} -> {resp.status}, not {{items, total, page, page_size}}")
        elif not (isinstance(body["page_size"], int) and len(body["items"]) <= body["page_size"] <= 50):
            problems.append(f"{template}: page_size {body['page_size']} with {len(body['items'])} items")
        for params in ({"page_size": 51}, {"page_size": 0}, {"page": 0}):
            status = w.call("GET", path, actor=admin, params=params).status
            if status != 422:
                problems.append(f"{template} {params} -> {status}, expected 422")
    emails = [str(u.get("email")) for u in w.items(admin, "/api/users")]
    if emails != sorted(emails):
        problems.append("accounts not sorted by email")
    detail = w.get(tid, admin)
    nested = [k for k, v in detail.items() if isinstance(v, list) and any(isinstance(x, dict) for x in v)]
    if nested:
        problems.append(f"ticket detail embeds collections {nested}")
    _problems(problems)


def arc_08(w: World) -> None:
    alice, admin = w.a("alice"), w.admin
    tid = w.ticket(alice)
    for i in range(4):
        expect(w.message(alice, tid, f"Message rapide {i}").status == 201, "message")
    ticket = w.get(tid, alice)
    messages = w.items(alice, f"/api/tickets/{tid}/messages")
    stamps = [("ticket.created_at", ticket.get("created_at")), ("ticket.updated_at", ticket.get("updated_at"))]
    stamps += [("message.created_at", m.get("created_at")) for m in messages]
    stamps += [("account.created_at", u.get("created_at")) for u in w.items(admin, "/api/users")[:3]]
    bad = [f"{name}={value!r}" for name, value in stamps
           if _parse_dt(value) is None or _parse_dt(value).utcoffset() != timedelta(0)]
    expect(not bad, f"dates not ISO 8601 UTC with an explicit offset: {bad[:3]}")
    keys = [(_parse_dt(m.get("created_at")), str(m.get("id"))) for m in messages]
    expect(keys == sorted(keys), "messages not ordered by (created_at, id)")


def ux_08(w: World) -> None:
    page = w.call("GET", "/")
    expect(page.status == 200 and '<div id="root">' in page.text, f"GET / -> {page.status}")
    scripts = _SCRIPT.findall(page.text)
    expect(scripts, "index.html references no script")
    bundle = ""
    for src in scripts:
        expect(not src.startswith(("http://", "https://", "//")), f"script loaded from another origin: {src}")
        resp = w.call("GET", "/" + src.lstrip("./"))
        expect(resp.status == 200, f"GET {src} -> {resp.status}")
        bundle += resp.text
    found = _BACKEND_URL.search(bundle)
    expect(not found, f"backend address hard-coded in the bundle: {found.group(0) if found else ''}")
    expect("/api/" in bundle, "the bundle never calls a relative /api/ path")


def ops_01(w: World) -> None:
    product = w.product
    expect(product.lock_present and product.sync_ok, "Python environment not rebuilt from uv.lock")
    expect(product.frontend and (product.frontend_dir / "package-lock.json").is_file(),
           "no frontend/package.json with package-lock.json")
    expect(product.frontend_ok, f"frontend not built from the lock: {product.frontend_detail[:300]}")


def ops_03(w: World) -> None:
    health = w.call("GET", HEALTH_PATH)
    expect(health.status == 200, f"GET {HEALTH_PATH} -> {health}")
    expect("@" not in health.text, "the health check exposes account data")
    for path in ("/api/tickets", "/api/dashboard", "/api/auth/me"):
        status = w.call("GET", path).status
        expect(status == 401, f"anonymous GET {path} -> {status}, expected 401")
    page = w.call("GET", "/")
    expect(page.status == 200 and '<div id="root">' in page.text, f"GET / -> {page.status}, built UI expected")
    expect(w.facts.get("bootstrap_rc") == 0, "the bootstrap command of the annex failed")


def ops_04_before(w: World) -> None:
    alice, camille = w.a("alice"), w.a("camille")
    tid = w.ticket(alice, title="Ticket persistant OPS-04")
    expect(w.message(alice, tid, "Réponse publique persistante").status == 201, "public message")
    expect(w.message(camille, tid, "Note interne persistante", "internal").status == 201, "internal note")
    w.facts["persisted"] = {"ticket": tid, "detail": w.get(tid),
                            "messages": sorted(w.ids(camille, f"/api/tickets/{tid}/messages")),
                            "history": w.history_total(tid), "users": w.total(w.admin, "/api/users")}


def ops_04_after(w: World) -> None:
    saved = w.facts.get("persisted")
    expect(saved, "nothing recorded before the restart")
    w.must_login(w.admin)
    tid = saved["ticket"]
    detail = w.get(tid)
    for key in ("title", "status", "version", "owner_id"):
        expect(detail.get(key) == saved["detail"].get(key), f"after restart {key}={detail.get(key)!r}, "
               f"before {saved['detail'].get(key)!r}")
    expect(sorted(w.ids(w.staff, f"/api/tickets/{tid}/messages")) == saved["messages"], "messages lost on restart")
    expect(w.history_total(tid) == saved["history"], "history changed on restart")
    expect(w.total(w.admin, "/api/users") == saved["users"], "accounts changed on restart")


# --------------------------------------------------------------------------- orchestration

PHASE1: list[tuple[str, str, Callable[[World], None]]] = [
    ("OPS-03", "server", ops_03), ("UX-08", "server", ux_08), ("SEC-05", "admin", sec_05),
    ("SEC-01", "admin", sec_01), ("SEC-08", "users", sec_08), ("SEC-07", "users", sec_07),
    ("SEC-06", "users", sec_06), ("SEC-02", "users", sec_02), ("SEC-03", "users", sec_03),
    ("SEC-11", "users", sec_11), ("SEC-12", "users", sec_12),
    ("SEC-14", "users", sec_14), ("FUN-01", "users", fun_01), ("FUN-02", "users", fun_02),
    ("SEC-09", "users", sec_09), ("SEC-10", "users", sec_10), ("FUN-03", "users", fun_03),
    ("FUN-04", "users", fun_04), ("FUN-05", "users", fun_05), ("FUN-13", "users", fun_13),
    ("FUN-06", "users", fun_06), ("FUN-07", "users", fun_07), ("FUN-09", "users", fun_09),
    ("FUN-10", "users", fun_10), ("FUN-11", "users", fun_11), ("FUN-12", "users", fun_12),
    ("ARC-07", "users", arc_07), ("ARC-08", "users", arc_08), ("OPS-04", "users", ops_04_before),
    ("SEC-13", "users", sec_13), ("ARC-03", "users", arc_03), ("ARC-06", "users", arc_06),
    ("SEC-15", "users", sec_15),
]


def _attempt(fn: Callable[[World], None], w: World) -> str:
    """Run one check body. Returns "" when it passed, else the failure detail."""
    try:
        fn(w)
        return ""
    except Fail as exc:
        return str(exc) or "failed"
    except Exception as exc:  # a crash of one check must not stop the others
        return f"{type(exc).__name__}: {exc}"


def checks(product: Product, tmp: Path) -> list[Check]:
    work = tmp / "b5"
    work.mkdir(parents=True, exist_ok=True)
    w = World(product, work / "relais.db")
    results: dict[str, Check] = {}
    late: dict[str, list[str]] = defaultdict(list)

    def run(cid: str, fn: Callable[[World], None], world: World) -> None:
        failure = _attempt(fn, world)
        results[cid] = Check(cid, not failure, failure)

    def run_late(cid: str, fn: Callable[[World], None], world: World, label: str) -> None:
        failure = _attempt(fn, world)
        if failure:
            late[cid].append(f"{label}: {failure}")

    run("OPS-01", ops_01, w)
    w.facts["bootstrap_no_credentials_rc"] = w.bootstrap(credentials=False).returncode
    w.facts["bootstrap_rc"] = w.bootstrap(credentials=True).returncode
    w.facts["bootstrap_again_rc"] = w.bootstrap(credentials=True, admin_email="autre-admin@relais.test").returncode

    blocked: dict[str, str] = {}
    try:
        with w.server():
            blocked["admin"] = w.setup_admin()
            blocked["users"] = blocked["admin"] or w.setup_users()
            for cid, stage, fn in PHASE1:
                reason = blocked.get(stage, "")
                if reason:
                    results[cid] = Check(cid, False, f"not run: {reason}")
                else:
                    run(cid, fn, w)
    except RuntimeError as exc:
        blocked["server"] = f"server: {exc}"

    if not blocked.get("server") and not blocked.get("users"):
        try:
            with w.server():  # same database, new process: what was written must still be there
                relogin = _attempt(lambda world: [world.must_login(world.a(n)) for n in ("alice", "camille")], w)
                if relogin:
                    late["OPS-04"].append(f"after restart: {relogin}")
                    late["FUN-07"].append(f"after restart: {relogin}")
                else:
                    run_late("OPS-04", ops_04_after, w, "after restart")
                    run_late("FUN-07", fun_07_after_restart, w, "after restart")
        except RuntimeError as exc:
            late["OPS-04"].append(f"restart: {exc}")
            late["FUN-07"].append(f"restart: {exc}")

    fresh = World(product, work / "fresh.db")  # SEC-04 needs a fresh failure counter and database
    rc = fresh.bootstrap(credentials=True).returncode
    if rc != 0:
        late["SEC-01"].append(f"create-admin on another blank database -> rc={rc}")
        results["SEC-04"] = Check("SEC-04", False, "not run: no admin on the fresh database")
    else:
        try:
            with fresh.server():
                reason = fresh.setup_admin()
                if reason:
                    results["SEC-04"] = Check("SEC-04", False, f"not run: {reason}")
                else:
                    run("SEC-04", sec_04, fresh)
        except RuntimeError as exc:
            results["SEC-04"] = Check("SEC-04", False, f"not run: fresh server: {exc}")

    out: list[Check] = []
    for cid in CRITERIA:
        if cid in NOT_AUTOMATED_IDS:
            out.append(Check(cid, False, NOT_AUTOMATED))
            continue
        check = results.get(cid) or Check(cid, False, f"not run: {blocked.get('server') or 'server phase'}")
        if late.get(cid):
            extra = "; ".join(late[cid])
            check = Check(cid, False, f"{check.detail}; {extra}" if check.detail else extra)
        out.append(check)
    return out
