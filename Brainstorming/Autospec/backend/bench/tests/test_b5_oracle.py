"""Mechanics of the B5 oracle (Relais Support), checked against a tiny stdlib stub server.

No reference product exists for B5 (too big): these tests prove that the oracle always
returns the 57 criteria in order, keeps NOT_AUTOMATED ones failed, passes what a stub
implements correctly, fails what it implements wrongly, and survives a product that
does not start.
"""

import re
import sys
from pathlib import Path

import pytest

from bench.briefs import load_brief, verify_all
from bench.oracle import NOT_AUTOMATED, Product
from bench.oracles import B5
from bench.paths import BENCH_DIR, REPO_DIR

REFERENTIAL = REPO_DIR / "docs" / "validation" / "support-client" / "02_requirements_verification.md"
SPEC = REPO_DIR / "docs" / "validation" / "support-client" / "01_specification.md"

STUB = r'''
import hashlib
import json
import os
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB = os.environ.get("RELAIS_DB", "relais.db")
PORT = int(os.environ.get("PORT", "8000"))
ORIGIN = os.environ.get("RELAIS_ORIGIN", f"http://127.0.0.1:{PORT}")
FLAGS = "HttpOnly; SameSite=Lax; Path=/"
SESSIONS = {}


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def load():
    try:
        with open(DB, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def create_admin():
    names = ("RELAIS_ADMIN_EMAIL", "RELAIS_ADMIN_NAME", "RELAIS_ADMIN_PASSWORD")
    email, name, password = (os.environ.get(n) for n in names)
    if not (email and name and password):
        print("identifiants manquants", file=sys.stderr)
        return 2
    data = load()
    if data.get("admin"):
        print("un administrateur existe deja", file=sys.stderr)
        return 1
    data["admin"] = {"id": "u-admin", "email": email.strip().lower(), "display_name": name,
                     "role": "admin", "active": True, "pw": digest(password)}
    with open(DB, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    return 0


def public(user):
    return {k: v for k, v in user.items() if k != "pw"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body=None, cookie=None):
        if isinstance(body, str):
            raw = body.encode()
        else:
            raw = json.dumps(body).encode() if body is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "text/html" if isinstance(body, str) else "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(raw)

    def fail(self, status, code):
        self.reply(status, {"error": {"code": code, "message": "Requete refusee"}})

    def session(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "sid" and digest(value) in SESSIONS:
                return digest(value), SESSIONS[digest(value)]
        return None, None

    def do_GET(self):
        if self.path == "/api/health":
            return self.reply(200, {"status": "ok"})
        if self.path == "/":
            return self.reply(200, '<!doctype html><html><body><div id="root"></div></body></html>')
        key, session = self.session()
        if session is None:
            return self.fail(401, "UNAUTHENTICATED")
        if self.path == "/api/auth/me":
            return self.reply(200, {"user": public(session["user"]), "csrf_token": session["csrf"]})
        return self.fail(404, "NOT_FOUND")

    def mutate(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.headers.get("Origin") != ORIGIN:
            return self.fail(403, "ORIGIN")
        if self.path == "/api/auth/login":
            admin = load().get("admin")
            if admin and body.get("email") == admin["email"] and digest(body.get("password")) == admin["pw"]:
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                SESSIONS[digest(token)] = {"user": admin, "csrf": csrf}
                return self.reply(200, {"user": public(admin), "csrf_token": csrf}, f"sid={token}; {FLAGS}")
            return self.fail(401, "BAD_CREDENTIALS")
        key, session = self.session()
        if self.path == "/api/auth/logout":
            if session is not None:
                if self.headers.get("X-CSRF-Token") != session["csrf"]:
                    return self.fail(403, "CSRF")
                del SESSIONS[key]
            return self.reply(204, None, "sid=; Max-Age=0; Path=/")
        if session is None:
            return self.fail(401, "UNAUTHENTICATED")
        if self.headers.get("X-CSRF-Token") != session["csrf"]:
            return self.fail(403, "CSRF")
        return self.fail(404, "NOT_FOUND")

    do_POST = do_PATCH = do_PUT = do_DELETE = mutate


if __name__ == "__main__":
    if sys.argv[1:] == ["create-admin"]:
        sys.exit(create_admin())
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
'''


class StubProduct(Product):
    """A product whose interpreter is the bench's own (the stub only needs the stdlib)."""

    @property
    def python(self) -> str:
        return sys.executable


def _stub(root: Path, source: str) -> StubProduct:
    package = root / "relais_support"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(source, encoding="utf-8")
    return StubProduct(dir=root, env_dir=root / "no-env", package="relais_support",
                       lock_present=False, sync_ok=True)


def _judge(tmp_path: Path, source: str) -> dict[str, dict]:
    product = _stub(tmp_path / "product", source)
    work = tmp_path / "work"
    work.mkdir()
    checks = B5.checks(product, work)
    assert [c.id for c in checks] == B5.CRITERIA
    return {c.id: {"passed": c.passed, "detail": c.detail} for c in checks}


def test_criteria_are_exactly_the_57_ids_of_the_referential():
    in_doc = re.findall(r"^\| ((?:SEC|FUN|ARC|UX|TST|OPS)-\d\d) \|", REFERENTIAL.read_text(encoding="utf-8"),
                        re.MULTILINE)
    assert len(B5.CRITERIA) == len(set(B5.CRITERIA)) == 57
    assert sorted(in_doc) == sorted(B5.CRITERIA)


def test_every_criterion_is_either_automated_by_a_phase_or_declared_not_automated():
    automated = {cid for cid, _stage, _fn in B5.PHASE1} | {"OPS-01", "SEC-04"}
    assert automated.isdisjoint(B5.NOT_AUTOMATED_IDS)
    assert automated | B5.NOT_AUTOMATED_IDS == set(B5.CRITERIA)
    assert len(automated) == 35


def test_the_coverage_document_explains_every_criterion():
    text = (BENCH_DIR / "oracles" / "B5_COVERAGE.md").read_text(encoding="utf-8")
    missing = [cid for cid in B5.CRITERIA if f"| {cid} |" not in text]
    assert not missing
    assert "\u2014" not in text


def test_stub_passes_what_it_implements_and_not_automated_criteria_stay_failed(tmp_path):
    results = _judge(tmp_path, STUB)

    not_automated = {cid for cid, r in results.items() if r["detail"] == NOT_AUTOMATED}
    assert not_automated == set(B5.NOT_AUTOMATED_IDS)
    assert not any(results[cid]["passed"] for cid in not_automated)
    passed = {cid for cid, r in results.items() if r["passed"]}
    assert passed == {"OPS-03", "SEC-05"}, {cid: r["detail"] for cid, r in results.items() if cid in passed}
    assert "GET /api/users" in results["SEC-01"]["detail"]
    assert results["FUN-01"]["detail"].startswith("not run: account setup")
    assert "lock" in results["OPS-01"]["detail"] or "uv.lock" in results["OPS-01"]["detail"]
    assert "sec04@relais.test" in results["SEC-04"]["detail"]


def test_a_stub_without_httponly_cookie_fails_the_session_criterion(tmp_path):
    results = _judge(tmp_path, STUB.replace('FLAGS = "HttpOnly; SameSite=Lax; Path=/"',
                                            'FLAGS = "SameSite=Lax; Path=/"'))

    assert not results["SEC-05"]["passed"]
    assert "HttpOnly" in results["SEC-05"]["detail"]
    assert results["OPS-03"]["passed"]


def test_a_product_that_does_not_start_still_reports_57_failed_criteria(tmp_path):
    broken = STUB.replace("    ThreadingHTTPServer((\"127.0.0.1\", PORT), Handler).serve_forever()",
                          "    sys.exit(3)")
    results = _judge(tmp_path, broken)

    assert not any(r["passed"] for r in results.values())
    assert "server exited with 3" in results["SEC-02"]["detail"]
    assert "server exited with 3" in results["SEC-04"]["detail"]


def test_b5_brief_carries_the_specification_verbatim_and_is_in_the_manifest():
    assert verify_all() == []
    brief = load_brief("B5")
    assert (brief.package, brief.profile) == ("relais_support", "fullstack")
    assert brief.refs == ["docs/validation/support-client/01_specification.md",
                          "docs/validation/support-client/02_requirements_verification.md"]
    spec = SPEC.read_text(encoding="utf-8").replace("\r\n", "\n").replace(" \u2014 ", " - ")
    assert brief.body.startswith(spec.rstrip("\n") + "\n")
    assert "\u2014" not in brief.body
    assert "python -m relais_support create-admin" in brief.body


@pytest.mark.parametrize("header, expired", [
    ("sid=; Max-Age=0; Path=/", True),
    ('sid=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/', True),
    ("sid=abc; HttpOnly; Path=/; SameSite=lax", False),
])
def test_set_cookie_parsing(header, expired):
    assert B5.parse_set_cookie(header).expired is expired
