"""Send one application email via Gmail SMTP (SSL), with a hard daily cap.

Run with:  venv\\Scripts\\python.exe scripts\\send_email.py --to a@b.c --subject "..." --body-file msg.md [--attach cv.pdf] [--reply-to x@y.z] [--bcc-self]

Credentials come from Prospector\\.env (GMAIL_ADDRESS, GMAIL_APP_PASSWORD,
DAILY_EMAIL_CAP — parsed with a tiny built-in parser, no python-dotenv).

Hard cap: counts today's applications rows with channel='email' and a sent_at
of today; refuses with exit code 2 (JSON error) when the cap is reached.
The password is never logged or printed.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import smtplib
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    """Tiny .env parser: KEY=VALUE lines, # comments, optional quotes."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        env[key.strip()] = value
    return env


def emails_sent_today() -> int:
    conn = db.get_conn()
    db.init_db(conn)
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM applications"
        " WHERE channel = 'email' AND sent_at IS NOT NULL"
        " AND date(sent_at) = date('now', 'localtime')").fetchone()
    conn.close()
    return int(row["n"]) if row else 0


def fail(payload: dict, code: int) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return code


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="send_email.py",
        description="Send one application email via Gmail SMTP (465/SSL), "
                    "enforcing the DAILY_EMAIL_CAP from .env")
    parser.add_argument("--to", required=True, help="recipient email address")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body-file", required=True,
                        help="path to the message body (markdown/plain, UTF-8)")
    parser.add_argument("--attach", action="append", default=[],
                        metavar="PDF", help="attachment path (repeatable)")
    parser.add_argument("--reply-to", dest="reply_to")
    parser.add_argument("--bcc-self", action="store_true",
                        help="BCC the sender address")
    args = parser.parse_args(argv)

    env = load_env()
    address = env.get("GMAIL_ADDRESS", "").strip()
    password = env.get("GMAIL_APP_PASSWORD", "").strip()
    if not address or not password:
        return fail({"sent": False,
                     "error": "GMAIL_ADDRESS / GMAIL_APP_PASSWORD missing in .env"}, 1)
    try:
        cap = int(env.get("DAILY_EMAIL_CAP", "5") or "5")
    except ValueError:
        cap = 5

    sent_today = emails_sent_today()
    if sent_today >= cap:
        return fail({"sent": False, "error": "daily email cap reached",
                     "sent_today": sent_today, "cap": cap,
                     "date": date.today().isoformat()}, 2)

    body_path = Path(args.body_file)
    if not body_path.exists():
        return fail({"sent": False,
                     "error": f"body file not found: {body_path}"}, 1)
    body = body_path.read_text(encoding="utf-8")

    msg = EmailMessage()
    msg["From"] = address
    msg["To"] = args.to
    msg["Subject"] = args.subject
    if args.reply_to:
        msg["Reply-To"] = args.reply_to
    if args.bcc_self:
        msg["Bcc"] = address
    msg.set_content(body)

    for attach_path in args.attach:
        p = Path(attach_path)
        if not p.exists():
            return fail({"sent": False,
                         "error": f"attachment not found: {p}"}, 1)
        ctype, _ = mimetypes.guess_type(p.name)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        msg.add_attachment(p.read_bytes(), maintype=maintype,
                           subtype=subtype, filename=p.name)

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=60) as smtp:
            smtp.login(address, password)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        return fail({"sent": False,
                     "error": "SMTP authentication failed (check app password"
                              " in .env — value not shown)"}, 1)
    except Exception as exc:
        return fail({"sent": False,
                     "error": f"{type(exc).__name__}: {exc}"}, 1)

    print(json.dumps({"sent": True, "to": args.to, "subject": args.subject,
                      "attachments": [Path(a).name for a in args.attach],
                      "sent_today_after": sent_today + 1, "cap": cap},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
