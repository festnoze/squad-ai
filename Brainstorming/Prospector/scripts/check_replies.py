"""Scan the Gmail INBOX over IMAP for replies to sent applications.

Run with:  venv\\Scripts\\python.exe scripts\\check_replies.py [--days 7] [--dry-run]

Matching is intentionally simple (candidate matches, not proof):
  - the From address appears in contacts.email, OR
  - the subject contains enough words from a sent mission's title.
Matches update applications.reply_at and set the mission status to 'replied'
unless --dry-run is given. Output is JSON. Credentials from .env
(GMAIL_ADDRESS / GMAIL_APP_PASSWORD); the password is never printed.
"""
from __future__ import annotations

import argparse
import email
import email.header
import email.utils
import imaplib
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402
from send_email import load_env  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

IMAP_HOST = "imap.gmail.com"

STOPWORDS = {"the", "a", "an", "for", "and", "of", "to", "in", "at", "on",
             "with", "de", "la", "le", "les", "des", "un", "une", "et",
             "pour", "en", "chez", "remote", "job", "mission", "re", "fwd"}


def decode_header_value(value: Optional[str]) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    out = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def title_words(title: str) -> set[str]:
    words = re.findall(r"[a-zà-ÿ0-9]{3,}", (title or "").lower())
    return {w for w in words if w not in STOPWORDS}


def subject_matches_title(subject: str, title: str) -> bool:
    """True when >= 2 significant title words (or the single one) appear."""
    twords = title_words(title)
    if not twords:
        return False
    swords = title_words(subject)
    overlap = twords & swords
    needed = 1 if len(twords) == 1 else 2
    return len(overlap) >= needed


def load_candidates() -> tuple[dict[str, list[dict[str, Any]]],
                               list[dict[str, Any]]]:
    """Returns (contacts by lowercased email, open sent applications)."""
    conn = db.get_conn()
    db.init_db(conn)
    contacts: dict[str, list[dict[str, Any]]] = {}
    for row in conn.execute(
            "SELECT * FROM contacts WHERE email IS NOT NULL"):
        contacts.setdefault(row["email"].strip().lower(), []).append(dict(row))
    apps = [dict(r) for r in conn.execute(
        "SELECT a.id AS application_id, a.mission_id, a.reply_at,"
        "       m.title AS mission_title, m.company AS mission_company"
        " FROM applications a LEFT JOIN missions m ON m.id = a.mission_id"
        " WHERE a.sent_at IS NOT NULL AND a.reply_at IS NULL")]
    conn.close()
    return contacts, apps


def mark_replied(application_id: int, mission_id: Optional[int],
                 reply_at: str) -> None:
    conn = db.get_conn()
    conn.execute("UPDATE applications SET reply_at = ? WHERE id = ?",
                 (reply_at, application_id))
    if mission_id:
        conn.execute(
            "UPDATE missions SET status = 'replied', updated_at = ?"
            " WHERE id = ?", (db.now_iso(), mission_id))
    conn.commit()
    conn.close()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_replies.py",
        description="IMAP-scan the Gmail INBOX for candidate replies to sent "
                    "applications; update reply_at / mission status")
    parser.add_argument("--days", type=int, default=7,
                        help="look at messages newer than N days (default 7)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report matches without writing to the DB")
    args = parser.parse_args(argv)

    env = load_env()
    address = env.get("GMAIL_ADDRESS", "").strip()
    password = env.get("GMAIL_APP_PASSWORD", "").strip()
    if not address or not password:
        print(json.dumps({"error": "GMAIL_ADDRESS / GMAIL_APP_PASSWORD"
                                   " missing in .env"}))
        return 1

    contacts, apps = load_candidates()
    if not apps and not contacts:
        print(json.dumps({"matches": [], "checked": 0,
                          "note": "no sent applications or contacts to match"}))
        return 0

    since = (datetime.now() - timedelta(days=args.days)).strftime("%d-%b-%Y")
    matches: list[dict[str, Any]] = []
    checked = 0
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST)
        imap.login(address, password)
        imap.select("INBOX", readonly=True)
        _, data = imap.search(None, f'(SINCE "{since}")')
        ids = data[0].split() if data and data[0] else []
        for msg_id in ids:
            _, msg_data = imap.fetch(
                msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            raw = b"".join(part[1] for part in msg_data
                           if isinstance(part, tuple))
            headers = email.message_from_bytes(raw)
            checked += 1
            from_name, from_addr = email.utils.parseaddr(
                decode_header_value(headers.get("From")))
            from_addr = from_addr.strip().lower()
            subject = decode_header_value(headers.get("Subject"))
            msg_date = decode_header_value(headers.get("Date"))
            if from_addr == address.lower():
                continue  # our own (bcc'd) messages

            matched_apps: list[dict[str, Any]] = []
            reason = None
            if from_addr in contacts:
                reason = "from-address in contacts"
                used_ids = {c.get("used_in_application_id")
                            for c in contacts[from_addr]}
                matched_apps = [a for a in apps
                                if a["application_id"] in used_ids] or apps[:1]
            else:
                for app in apps:
                    if subject_matches_title(subject,
                                             app.get("mission_title") or ""):
                        reason = "subject matches mission title"
                        matched_apps.append(app)
            if not matched_apps:
                continue

            reply_at = db.now_iso()
            try:
                parsed = email.utils.parsedate_to_datetime(msg_date)
                reply_at = parsed.astimezone().isoformat(timespec="seconds")
            except Exception:
                pass

            for app in matched_apps:
                matches.append({
                    "application_id": app["application_id"],
                    "mission_id": app.get("mission_id"),
                    "mission_title": app.get("mission_title"),
                    "from": from_addr,
                    "from_name": from_name,
                    "subject": subject,
                    "date": msg_date,
                    "reason": reason,
                    "updated": not args.dry_run,
                })
                if not args.dry_run:
                    mark_replied(app["application_id"],
                                 app.get("mission_id"), reply_at)
        imap.logout()
    except imaplib.IMAP4.error as exc:
        print(json.dumps({"error": f"IMAP error: {exc} (check app password"
                                   " in .env — value not shown)"}))
        return 1
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 1

    print(json.dumps({"checked": checked, "since_days": args.days,
                      "dry_run": args.dry_run, "matches": matches},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
