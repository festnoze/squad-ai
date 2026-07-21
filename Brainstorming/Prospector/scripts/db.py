"""Prospector SQLite database CLI.

Run with:  venv\\Scripts\\python.exe scripts\\db.py <command> [options]

All output is machine-readable JSON (one object or array per invocation)
so Claude agents can parse it. Stdlib only.

Commands:
  init             create the schema (idempotent)
  upsert-mission   read JSON object/array from stdin or --file, dedup by hash
  list-missions    --status X [--min-score N] [--limit N]
  set-status       --id N --status X
  set-score        --id N --score F --breakdown JSON
  add-application  args or stdin JSON
  update-application --id N --set key=value ...
  add-contact      stdin JSON or args
  list-contacts    --company X
  log-run          --source S --found N --new N --errors TEXT
  stats            counts by status, per-source runs, applications summary
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "prospector.db"

MISSION_STATUSES = (
    "new", "scored", "drafted", "queued", "sent", "replied",
    "interview", "won", "lost", "ignored",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS missions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT,
    url TEXT,
    title TEXT,
    company TEXT,
    location TEXT,
    remote_policy TEXT,
    language TEXT CHECK (language IN ('fr', 'en') OR language IS NULL),
    engagement TEXT,
    rate TEXT,
    description TEXT,
    stack TEXT,
    found_at TEXT,
    hash TEXT UNIQUE,
    score REAL,
    score_breakdown TEXT,
    status TEXT DEFAULT 'new',
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id INTEGER REFERENCES missions(id),
    channel TEXT,
    language TEXT,
    cv_variant TEXT,
    message_path TEXT,
    sent_at TEXT,
    followup_count INTEGER DEFAULT 0,
    last_followup_at TEXT,
    reply_at TEXT,
    outcome TEXT
);
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT,
    name TEXT,
    role TEXT,
    email TEXT,
    source TEXT,
    used_in_application_id INTEGER
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    finished_at TEXT,
    source TEXT,
    missions_found INTEGER,
    new_missions INTEGER,
    errors TEXT
);
CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
CREATE INDEX IF NOT EXISTS idx_missions_hash ON missions(hash);
CREATE INDEX IF NOT EXISTS idx_applications_mission ON applications(mission_id);
"""


def now_iso() -> str:
    """ISO 8601 local timestamp, seconds precision."""
    return datetime.now().isoformat(timespec="seconds")


def get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: Optional[sqlite3.Connection] = None) -> None:
    own = conn is None
    conn = conn or get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    if own:
        conn.close()


def normalize_url(url: str) -> str:
    url = url.strip().lower()
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
            break
    if url.startswith("www."):
        url = url[4:]
    # strip tracking query strings
    if "?" in url:
        base, _, query = url.partition("?")
        kept = [
            p for p in query.split("&")
            if p and not p.startswith(("utm_", "ref=", "source=", "gh_src="))
        ]
        url = base + ("?" + "&".join(kept) if kept else "")
    if url.endswith("/"):
        url = url[:-1]
    return url


def mission_hash(mission: dict[str, Any]) -> str:
    url = (mission.get("url") or "").strip()
    if url:
        basis = normalize_url(url)
    else:
        basis = ((mission.get("title") or "").strip().lower()
                 + "|" + (mission.get("company") or "").strip().lower())
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def upsert_missions(missions: list[dict[str, Any]],
                    conn: Optional[sqlite3.Connection] = None) -> dict[str, int]:
    """INSERT OR IGNORE each mission (dedup by hash). Returns counts."""
    own = conn is None
    conn = conn or get_conn()
    init_db(conn)
    inserted = 0
    skipped = 0
    for m in missions:
        h = m.get("hash") or mission_hash(m)
        stack = m.get("stack")
        if isinstance(stack, (list, dict)):
            stack = json.dumps(stack, ensure_ascii=False)
        breakdown = m.get("score_breakdown")
        if isinstance(breakdown, (list, dict)):
            breakdown = json.dumps(breakdown, ensure_ascii=False)
        cur = conn.execute(
            """INSERT OR IGNORE INTO missions
               (source, url, title, company, location, remote_policy, language,
                engagement, rate, description, stack, found_at, hash, score,
                score_breakdown, status, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                m.get("source"), m.get("url"), m.get("title"), m.get("company"),
                m.get("location"), m.get("remote_policy"), m.get("language"),
                m.get("engagement"), m.get("rate"), m.get("description"),
                stack, m.get("found_at") or now_iso(), h, m.get("score"),
                breakdown, m.get("status") or "new", now_iso(),
            ),
        )
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1
    conn.commit()
    if own:
        conn.close()
    return {"inserted": inserted, "skipped": skipped}


def log_run(source: str, found: int, new: int, errors: str = "",
            started_at: Optional[str] = None,
            conn: Optional[sqlite3.Connection] = None) -> int:
    own = conn is None
    conn = conn or get_conn()
    init_db(conn)
    cur = conn.execute(
        "INSERT INTO runs (started_at, finished_at, source, missions_found,"
        " new_missions, errors) VALUES (?,?,?,?,?,?)",
        (started_at or now_iso(), now_iso(), source, found, new, errors or None),
    )
    conn.commit()
    run_id = int(cur.lastrowid or 0)
    if own:
        conn.close()
    return run_id


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def _read_json_input(file_arg: Optional[str]) -> Any:
    if file_arg:
        text = Path(file_arg).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    return json.loads(text)


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- commands

def cmd_init(_args: argparse.Namespace) -> int:
    init_db()
    _print({"ok": True, "db": str(DB_PATH)})
    return 0


def cmd_upsert_mission(args: argparse.Namespace) -> int:
    data = _read_json_input(args.file)
    missions = data if isinstance(data, list) else [data]
    _print(upsert_missions(missions))
    return 0


def cmd_list_missions(args: argparse.Namespace) -> int:
    conn = get_conn()
    init_db(conn)
    sql = "SELECT * FROM missions WHERE 1=1"
    params: list[Any] = []
    if args.status:
        sql += " AND status = ?"
        params.append(args.status)
    if args.min_score is not None:
        sql += " AND score >= ?"
        params.append(args.min_score)
    sql += " ORDER BY score DESC NULLS LAST, id DESC"
    if args.limit:
        sql += " LIMIT ?"
        params.append(args.limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    _print(_rows_to_dicts(rows))
    return 0


def cmd_set_status(args: argparse.Namespace) -> int:
    if args.status not in MISSION_STATUSES:
        _print({"error": f"invalid status '{args.status}'",
                "valid": list(MISSION_STATUSES)})
        return 1
    conn = get_conn()
    init_db(conn)
    cur = conn.execute(
        "UPDATE missions SET status = ?, updated_at = ? WHERE id = ?",
        (args.status, now_iso(), args.id),
    )
    conn.commit()
    conn.close()
    _print({"ok": bool(cur.rowcount), "id": args.id, "status": args.status})
    return 0 if cur.rowcount else 1


def cmd_set_score(args: argparse.Namespace) -> int:
    breakdown = args.breakdown
    if breakdown:
        try:
            json.loads(breakdown)
        except json.JSONDecodeError:
            _print({"error": "--breakdown is not valid JSON"})
            return 1
    conn = get_conn()
    init_db(conn)
    cur = conn.execute(
        "UPDATE missions SET score = ?, score_breakdown = ?, updated_at = ?"
        " WHERE id = ?",
        (args.score, breakdown, now_iso(), args.id),
    )
    conn.commit()
    conn.close()
    _print({"ok": bool(cur.rowcount), "id": args.id, "score": args.score})
    return 0 if cur.rowcount else 1


APPLICATION_FIELDS = ("mission_id", "channel", "language", "cv_variant",
                      "message_path", "sent_at", "followup_count",
                      "last_followup_at", "reply_at", "outcome")


def cmd_add_application(args: argparse.Namespace) -> int:
    if args.stdin:
        data = _read_json_input(None)
    else:
        data = {k: getattr(args, k) for k in APPLICATION_FIELDS
                if getattr(args, k, None) is not None}
    if not data.get("mission_id"):
        _print({"error": "mission_id is required"})
        return 1
    conn = get_conn()
    init_db(conn)
    fields = [k for k in APPLICATION_FIELDS if k in data]
    cur = conn.execute(
        f"INSERT INTO applications ({', '.join(fields)})"
        f" VALUES ({', '.join('?' for _ in fields)})",
        [data[k] for k in fields],
    )
    conn.commit()
    app_id = cur.lastrowid
    conn.close()
    _print({"ok": True, "id": app_id})
    return 0


def cmd_update_application(args: argparse.Namespace) -> int:
    updates: dict[str, Any] = {}
    for pair in args.set:
        if "=" not in pair:
            _print({"error": f"bad --set '{pair}', expected key=value"})
            return 1
        key, _, value = pair.partition("=")
        if key not in APPLICATION_FIELDS:
            _print({"error": f"unknown field '{key}'",
                    "valid": list(APPLICATION_FIELDS)})
            return 1
        updates[key] = value
    if not updates:
        _print({"error": "nothing to update"})
        return 1
    conn = get_conn()
    init_db(conn)
    assignments = ", ".join(f"{k} = ?" for k in updates)
    cur = conn.execute(
        f"UPDATE applications SET {assignments} WHERE id = ?",
        [*updates.values(), args.id],
    )
    conn.commit()
    conn.close()
    _print({"ok": bool(cur.rowcount), "id": args.id, "updated": updates})
    return 0 if cur.rowcount else 1


CONTACT_FIELDS = ("company", "name", "role", "email", "source",
                  "used_in_application_id")


def cmd_add_contact(args: argparse.Namespace) -> int:
    if args.stdin:
        data = _read_json_input(None)
    else:
        data = {k: getattr(args, k) for k in CONTACT_FIELDS
                if getattr(args, k, None) is not None}
    if not data:
        _print({"error": "no contact data given (use args or --stdin)"})
        return 1
    conn = get_conn()
    init_db(conn)
    fields = [k for k in CONTACT_FIELDS if k in data]
    cur = conn.execute(
        f"INSERT INTO contacts ({', '.join(fields)})"
        f" VALUES ({', '.join('?' for _ in fields)})",
        [data[k] for k in fields],
    )
    conn.commit()
    contact_id = cur.lastrowid
    conn.close()
    _print({"ok": True, "id": contact_id})
    return 0


def cmd_list_contacts(args: argparse.Namespace) -> int:
    conn = get_conn()
    init_db(conn)
    if args.company:
        rows = conn.execute(
            "SELECT * FROM contacts WHERE lower(company) = lower(?)",
            (args.company,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM contacts").fetchall()
    conn.close()
    _print(_rows_to_dicts(rows))
    return 0


def cmd_log_run(args: argparse.Namespace) -> int:
    run_id = log_run(args.source, args.found, args.new, args.errors or "")
    _print({"ok": True, "id": run_id})
    return 0


def cmd_stats(_args: argparse.Namespace) -> int:
    conn = get_conn()
    init_db(conn)
    by_status = {
        r["status"]: r["n"]
        for r in conn.execute(
            "SELECT status, COUNT(*) AS n FROM missions GROUP BY status")
    }
    runs = _rows_to_dicts(conn.execute(
        "SELECT source, COUNT(*) AS runs, SUM(missions_found) AS found,"
        " SUM(new_missions) AS new, MAX(finished_at) AS last_run"
        " FROM runs GROUP BY source").fetchall())
    apps = conn.execute(
        "SELECT COUNT(*) AS total,"
        " SUM(CASE WHEN sent_at IS NOT NULL THEN 1 ELSE 0 END) AS sent,"
        " SUM(CASE WHEN reply_at IS NOT NULL THEN 1 ELSE 0 END) AS replied"
        " FROM applications").fetchone()
    conn.close()
    _print({
        "missions_by_status": by_status,
        "missions_total": sum(by_status.values()),
        "runs_by_source": runs,
        "applications": dict(apps) if apps else {},
    })
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="db.py", description="Prospector SQLite database CLI (JSON I/O)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the schema").set_defaults(func=cmd_init)

    up = sub.add_parser("upsert-mission",
                        help="insert mission(s) from stdin/--file JSON, dedup by hash")
    up.add_argument("--file", help="JSON file (default: stdin)")
    up.set_defaults(func=cmd_upsert_mission)

    lm = sub.add_parser("list-missions", help="list missions as JSON array")
    lm.add_argument("--status", choices=MISSION_STATUSES)
    lm.add_argument("--min-score", type=float, dest="min_score")
    lm.add_argument("--limit", type=int)
    lm.set_defaults(func=cmd_list_missions)

    ss = sub.add_parser("set-status", help="set a mission's status")
    ss.add_argument("--id", type=int, required=True)
    ss.add_argument("--status", required=True)
    ss.set_defaults(func=cmd_set_status)

    sc = sub.add_parser("set-score", help="set a mission's score + breakdown")
    sc.add_argument("--id", type=int, required=True)
    sc.add_argument("--score", type=float, required=True)
    sc.add_argument("--breakdown", help="JSON string")
    sc.set_defaults(func=cmd_set_score)

    aa = sub.add_parser("add-application", help="create an application row")
    aa.add_argument("--stdin", action="store_true", help="read JSON from stdin")
    aa.add_argument("--mission-id", type=int, dest="mission_id")
    aa.add_argument("--channel")
    aa.add_argument("--language")
    aa.add_argument("--cv-variant", dest="cv_variant")
    aa.add_argument("--message-path", dest="message_path")
    aa.add_argument("--sent-at", dest="sent_at")
    aa.set_defaults(func=cmd_add_application)

    ua = sub.add_parser("update-application", help="update application fields")
    ua.add_argument("--id", type=int, required=True)
    ua.add_argument("--set", nargs="+", required=True, metavar="key=value")
    ua.set_defaults(func=cmd_update_application)

    ac = sub.add_parser("add-contact", help="create a contact row")
    ac.add_argument("--stdin", action="store_true", help="read JSON from stdin")
    ac.add_argument("--company")
    ac.add_argument("--name")
    ac.add_argument("--role")
    ac.add_argument("--email")
    ac.add_argument("--source")
    ac.set_defaults(func=cmd_add_contact)

    lc = sub.add_parser("list-contacts", help="list contacts as JSON array")
    lc.add_argument("--company")
    lc.set_defaults(func=cmd_list_contacts)

    lr = sub.add_parser("log-run", help="record a scout run")
    lr.add_argument("--source", required=True)
    lr.add_argument("--found", type=int, default=0)
    lr.add_argument("--new", type=int, default=0)
    lr.add_argument("--errors", default="")
    lr.set_defaults(func=cmd_log_run)

    sub.add_parser("stats", help="summary counts").set_defaults(func=cmd_stats)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
