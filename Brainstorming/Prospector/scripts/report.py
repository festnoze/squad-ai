"""Daily digest: markdown report to stdout + logs\\digest_YYYY-MM-DD.md.

Run with:  venv\\Scripts\\python.exe scripts\\report.py [--no-write]

Sections: new missions today by source, top scored not-yet-drafted missions,
queue folder counts, applications sent this week, replies, follow-ups due
(sent > 5 days ago, no reply, followup_count < 2).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ROOT = Path(__file__).resolve().parent.parent
QUEUE_DIR = ROOT / "data" / "queue"
LOGS_DIR = ROOT / "logs"

FOLLOWUP_AFTER_DAYS = 5
MAX_FOLLOWUPS = 2


def queue_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for folder in ("pending", "approved", "sent", "rejected"):
        path = QUEUE_DIR / folder
        counts[folder] = (
            len([f for f in path.iterdir()
                 if f.is_file() and f.name != ".gitkeep"])
            if path.exists() else 0)
    return counts


def build_report(today: date) -> str:
    conn = db.get_conn()
    db.init_db(conn)

    new_today = conn.execute(
        "SELECT source, COUNT(*) AS n FROM missions"
        " WHERE date(found_at) = ? GROUP BY source ORDER BY n DESC",
        (today.isoformat(),)).fetchall()

    top_undrafted = conn.execute(
        "SELECT id, title, company, source, score FROM missions"
        " WHERE status IN ('new', 'scored') AND score IS NOT NULL"
        " ORDER BY score DESC LIMIT 10").fetchall()

    week_ago = (today - timedelta(days=7)).isoformat()
    sent_week = conn.execute(
        "SELECT a.id, a.sent_at, a.channel, m.title, m.company"
        " FROM applications a LEFT JOIN missions m ON m.id = a.mission_id"
        " WHERE a.sent_at IS NOT NULL AND date(a.sent_at) >= ?"
        " ORDER BY a.sent_at DESC", (week_ago,)).fetchall()

    replies = conn.execute(
        "SELECT a.id, a.reply_at, m.title, m.company"
        " FROM applications a LEFT JOIN missions m ON m.id = a.mission_id"
        " WHERE a.reply_at IS NOT NULL ORDER BY a.reply_at DESC LIMIT 10"
    ).fetchall()

    followup_cutoff = (datetime.now()
                       - timedelta(days=FOLLOWUP_AFTER_DAYS)).isoformat(
                           timespec="seconds")
    followups_due = conn.execute(
        "SELECT a.id, a.mission_id, a.sent_at, a.followup_count,"
        "       m.title, m.company"
        " FROM applications a LEFT JOIN missions m ON m.id = a.mission_id"
        " WHERE a.sent_at IS NOT NULL AND a.reply_at IS NULL"
        "   AND a.sent_at < ? AND a.followup_count < ?"
        " ORDER BY a.sent_at", (followup_cutoff, MAX_FOLLOWUPS)).fetchall()
    conn.close()

    q = queue_counts()
    lines: list[str] = []
    add = lines.append
    add(f"# Prospector digest — {today.isoformat()}")
    add("")

    add("## New missions today")
    if new_today:
        for r in new_today:
            add(f"- **{r['source']}**: {r['n']}")
    else:
        add("- none")
    add("")

    add("## Top scored missions (not yet drafted)")
    if top_undrafted:
        add("| id | score | title | company | source |")
        add("|---|---|---|---|---|")
        for r in top_undrafted:
            add(f"| {r['id']} | {r['score']:.1f} | {r['title'] or '?'} |"
                f" {r['company'] or '?'} | {r['source'] or '?'} |")
    else:
        add("- none")
    add("")

    add("## Queue")
    add(f"- pending: {q['pending']} | approved: {q['approved']} |"
        f" sent: {q['sent']} | rejected: {q['rejected']}")
    add("")

    add("## Applications sent this week")
    if sent_week:
        for r in sent_week:
            add(f"- [{r['sent_at']}] #{r['id']} {r['title'] or '?'}"
                f" @ {r['company'] or '?'} via {r['channel'] or '?'}")
    else:
        add("- none")
    add("")

    add("## Replies")
    if replies:
        for r in replies:
            add(f"- [{r['reply_at']}] #{r['id']} {r['title'] or '?'}"
                f" @ {r['company'] or '?'}")
    else:
        add("- none")
    add("")

    add(f"## Follow-ups due (> {FOLLOWUP_AFTER_DAYS} days, no reply,"
        f" < {MAX_FOLLOWUPS} follow-ups)")
    if followups_due:
        for r in followups_due:
            add(f"- app #{r['id']} (mission #{r['mission_id']})"
                f" {r['title'] or '?'} @ {r['company'] or '?'}"
                f" — sent {r['sent_at']},"
                f" follow-ups so far: {r['followup_count']}")
    else:
        add("- none")
    add("")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="report.py",
        description="Print the daily digest (markdown) and write it to "
                    "logs/digest_YYYY-MM-DD.md")
    parser.add_argument("--no-write", action="store_true",
                        help="print only, do not write the logs/ file")
    args = parser.parse_args(argv)

    today = date.today()
    report = build_report(today)
    print(report)
    if not args.no_write:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        out = LOGS_DIR / f"digest_{today.isoformat()}.md"
        out.write_text(report, encoding="utf-8")
        print(f"\n[written to {out}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
