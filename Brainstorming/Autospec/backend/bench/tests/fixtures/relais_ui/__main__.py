"""Relais Support stub for the bench's own tests, run as `python -m relais_support`.

Just enough of the bench annex's API, in memory (only the first admin is written to
RELAIS_DB, by `create-admin`), and index.html: a small vanilla JS page implementing the UX
behaviours of the specification. It is not a reference product: it exists to prove that
bench/oracles/b5_ui.py passes what is implemented and fails what is broken, the defects
being switched on in index.html (DEFECTS).
"""

import hashlib
import json
import os
import secrets
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB = Path(os.environ.get("RELAIS_DB", "relais.db"))
PORT = int(os.environ.get("PORT", "8000"))
PAGE = Path(__file__).with_name("index.html")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def create_admin() -> int:
    names = ("RELAIS_ADMIN_EMAIL", "RELAIS_ADMIN_NAME", "RELAIS_ADMIN_PASSWORD")
    email, name, password = (os.environ.get(n, "") for n in names)
    if not (email and name and password):
        print("identifiants manquants", file=sys.stderr)
        return 2
    if DB.is_file():
        print("un administrateur existe déjà", file=sys.stderr)
        return 1
    admin = {"id": str(uuid.uuid4()), "email": email.strip().lower(), "display_name": name, "role": "admin",
             "active": True, "created_at": now(), "pw": digest(password)}
    DB.write_text(json.dumps({"admin": admin}), encoding="utf-8")
    return 0


def create_app():
    from fastapi import Body, FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    lock = threading.Lock()
    users: dict[str, dict] = {}
    if DB.is_file():
        admin = json.loads(DB.read_text(encoding="utf-8"))["admin"]
        users[admin["id"]] = admin
    sessions: dict[str, dict] = {}  # cookie token -> {"user", "csrf"}
    tickets: dict[str, dict] = {}
    keys: dict[tuple[str, str], str] = {}  # (user id, client_request_id) -> ticket id
    clock = [0]  # update order, the newest ticket has the highest value
    app = FastAPI()

    def reply(status: int, body: object = None) -> Response:
        response = Response(status_code=status) if body is None else JSONResponse(body, status_code=status)
        response.headers["Cache-Control"] = "no-store"
        return response

    def fail(status: int, code: str, fields: dict | None = None) -> Response:
        error = {"code": code, "message": "Requête refusée", **({"fields": fields} if fields else {})}
        return reply(status, {"error": error})

    def public(user: dict) -> dict:
        return {k: v for k, v in user.items() if k != "pw"}

    def shown(ticket: dict) -> dict:
        return {k: v for k, v in ticket.items() if k != "order"}

    def caller(request: Request, *, staff: bool = False, admin: bool = False) -> tuple[dict | None, Response | None]:
        session = sessions.get(request.cookies.get("sid", ""))
        if session is None:
            return None, fail(401, "UNAUTHENTICATED")
        if request.method != "GET" and request.headers.get("x-csrf-token") != session["csrf"]:
            return None, fail(403, "CSRF")
        user = users[session["user"]]
        if (admin and user["role"] != "admin") or (staff and user["role"] == "client"):
            return None, fail(403, "FORBIDDEN")
        return user, None

    def visible(user: dict) -> list[dict]:
        return [t for t in tickets.values() if user["role"] != "client" or t["owner_id"] == user["id"]]

    def paginate(items: list, request: Request) -> dict:
        number = max(1, int(request.query_params.get("page", "1")))
        size = min(50, max(1, int(request.query_params.get("page_size", "20"))))
        return {"items": items[(number - 1) * size:number * size], "total": len(items), "page": number,
                "page_size": size}

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def index():
        return HTMLResponse(PAGE.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})

    @app.post("/api/auth/login")
    def login(body: dict = Body(...)):
        email = str(body.get("email", "")).strip().lower()
        user = next((u for u in users.values() if u["email"] == email), None)
        if user is None or user["pw"] != digest(str(body.get("password", ""))):
            return fail(401, "BAD_CREDENTIALS")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        sessions[token] = {"user": user["id"], "csrf": csrf}
        response = reply(200, {"user": public(user), "csrf_token": csrf})
        response.set_cookie("sid", token, httponly=True, samesite="lax", path="/")
        return response

    @app.post("/api/auth/logout")
    def logout(request: Request):
        token = request.cookies.get("sid", "")
        session = sessions.get(token)
        if session is not None and request.headers.get("x-csrf-token") != session["csrf"]:
            return fail(403, "CSRF")
        sessions.pop(token, None)
        response = reply(204)
        response.delete_cookie("sid", path="/")
        return response

    @app.get("/api/auth/me")
    def me(request: Request):
        user, error = caller(request)
        if error:
            return error
        return reply(200, {"user": public(user), "csrf_token": sessions[request.cookies["sid"]]["csrf"]})

    @app.get("/api/users")
    def list_users(request: Request):
        user, error = caller(request, admin=True)
        if error:
            return error
        return reply(200, paginate(sorted((public(u) for u in users.values()), key=lambda u: u["email"]), request))

    @app.post("/api/users")
    def create_user(request: Request, body: dict = Body(...)):
        user, error = caller(request, admin=True)
        if error:
            return error
        email = str(body.get("email", "")).strip().lower()
        with lock:
            if any(u["email"] == email for u in users.values()):
                return fail(409, "EMAIL_TAKEN")
            new = {"id": str(uuid.uuid4()), "email": email, "display_name": body.get("display_name", ""),
                   "role": body.get("role", "client"), "active": True, "created_at": now(),
                   "pw": digest(str(body.get("password", "")))}
            users[new["id"]] = new
        return reply(201, public(new))

    @app.get("/api/tickets")
    def list_tickets(request: Request):
        user, error = caller(request)
        if error:
            return error
        q = request.query_params.get("q", "").casefold()
        found = [t for t in visible(user) if q in f"{t['title']} {t['description']}".casefold()]
        found.sort(key=lambda t: t["order"], reverse=True)
        return reply(200, paginate([shown(t) for t in found], request))

    @app.post("/api/tickets")
    def create_ticket(request: Request, body: dict = Body(...)):
        user, error = caller(request)
        if error:
            return error
        if user["role"] != "client":
            return fail(403, "FORBIDDEN")
        title, description = str(body.get("title", "")).strip(), str(body.get("description", "")).strip()
        fields = {}
        if not 5 <= len(title) <= 120:
            fields["title"] = "Le titre doit contenir 5 à 120 caractères."
        if not 20 <= len(description) <= 5000:
            fields["description"] = "La description doit contenir 20 à 5000 caractères."
        if fields:
            return fail(422, "VALIDATION", fields)
        key = (user["id"], str(body.get("client_request_id", "")))
        with lock:
            if key in keys:
                return reply(200, shown(tickets[keys[key]]))
            clock[0] += 1
            ticket = {"id": str(uuid.uuid4()), "title": title, "description": description, "owner_id": user["id"],
                      "status": "open", "priority": "normal", "assignee_id": None, "created_at": now(),
                      "updated_at": now(), "version": 1, "order": clock[0]}
            tickets[ticket["id"]] = ticket
            keys[key] = ticket["id"]
        return reply(201, shown(ticket))

    @app.get("/api/tickets/{tid}")
    def get_ticket(tid: str, request: Request):
        user, error = caller(request)
        if error:
            return error
        ticket = tickets.get(tid)
        if ticket is None or ticket not in visible(user):
            return fail(404, "NOT_FOUND")
        return reply(200, shown(ticket))

    @app.patch("/api/tickets/{tid}")
    def patch_ticket(tid: str, request: Request, body: dict = Body(...)):
        user, error = caller(request, staff=True)
        if error:
            return error
        with lock:
            ticket = tickets.get(tid)
            if ticket is None:
                return fail(404, "NOT_FOUND")
            if body.get("expected_version") != ticket["version"]:
                return fail(409, "VERSION_CONFLICT")
            changes = {k: body[k] for k in ("priority", "status", "assignee_id") if k in body and body[k] != ticket[k]}
            if changes:
                clock[0] += 1
                ticket.update(changes, version=ticket["version"] + 1, order=clock[0], updated_at=now())
        return reply(200, shown(ticket))

    @app.get("/api/tickets/{tid}/messages")
    def messages(tid: str, request: Request):
        user, error = caller(request)
        if error:
            return error
        if tid not in tickets or tickets[tid] not in visible(user):
            return fail(404, "NOT_FOUND")
        return reply(200, paginate([], request))

    return app


if __name__ == "__main__":
    if sys.argv[1:] == ["create-admin"]:
        sys.exit(create_admin())
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=PORT, log_level="warning")
