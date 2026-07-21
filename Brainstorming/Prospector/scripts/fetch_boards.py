"""Fetch remote-job boards (no login) and upsert missions into the DB.

Run with:  venv\\Scripts\\python.exe scripts\\fetch_boards.py [--dry-run] [--limit N]

Sources (each isolated — one failing never kills the run):
  - RemoteOK API        https://remoteok.com/api
  - Remotive API        https://remotive.com/api/remote-jobs?search=ai
  - WeWorkRemotely RSS  https://weworkremotely.com/categories/remote-programming-jobs.rss
  - Hacker News "Who is hiring": TODO (see bottom of file)

Keywords come from config\\targets.yaml (sources.boards.keywords) with a
built-in fallback. Missions matching keywords are upserted via scripts\\db.py
(in-process import); --dry-run prints them as JSON instead.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ROOT = Path(__file__).resolve().parent.parent
TARGETS_YAML = ROOT / "config" / "targets.yaml"

DEFAULT_KEYWORDS = [
    "ai", "llm", "machine learning", "genai", "rag", "python",
    "ai engineer", "forward deployed",
]

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "Prospector/1.0 (freelance mission prospection)")
TIMEOUT = 30


def load_keywords() -> list[str]:
    """Keywords from config/targets.yaml (sources.boards.keywords) or defaults."""
    if TARGETS_YAML.exists():
        try:
            import yaml
            cfg = yaml.safe_load(TARGETS_YAML.read_text(encoding="utf-8")) or {}
            kws = (((cfg.get("sources") or {}).get("boards") or {})
                   .get("keywords"))
            if isinstance(kws, list) and kws:
                return [str(k).lower() for k in kws]
        except Exception as exc:  # config problems must not kill the run
            print(f"warning: could not read {TARGETS_YAML}: {exc}",
                  file=sys.stderr)
    return DEFAULT_KEYWORDS


def strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def matches_keywords(mission: dict[str, Any], keywords: list[str],
                     extra: str = "") -> bool:
    haystack = " ".join([
        mission.get("title") or "",
        mission.get("description") or "",
        extra,
    ]).lower()
    # Whole-word match so 'ai' does not hit 'email', 'maintain', 'said'...
    return any(
        re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", haystack)
        for kw in keywords
    )


def detect_engagement(*texts: Optional[str]) -> str:
    blob = " ".join(t or "" for t in texts).lower()
    if any(w in blob for w in ("freelance", "contract", "contractor",
                               "b2b", "consultant")):
        return "contract"
    return "unknown"


# ---------------------------------------------------------------- sources

def fetch_remoteok(keywords: list[str]) -> list[dict[str, Any]]:
    """RemoteOK JSON API. First element is metadata — skipped."""
    resp = requests.get("https://remoteok.com/api",
                        headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    items = resp.json()
    missions: list[dict[str, Any]] = []
    for item in items[1:]:  # index 0 is the legal/metadata blob
        if not isinstance(item, dict):
            continue
        tags = " ".join(item.get("tags") or [])
        mission = {
            "source": "remoteok",
            "url": item.get("url") or item.get("apply_url"),
            "title": item.get("position") or item.get("title"),
            "company": item.get("company"),
            "location": item.get("location") or "Remote",
            "remote_policy": "remote",
            "language": "en",
            "engagement": detect_engagement(item.get("position"),
                                            item.get("description"), tags),
            "rate": item.get("salary_min") and
                    f"{item.get('salary_min')}-{item.get('salary_max')} USD/yr" or None,
            "description": strip_html(item.get("description") or "")[:5000],
            "stack": json.dumps(item.get("tags") or [], ensure_ascii=False),
        }
        if matches_keywords(mission, keywords, extra=tags):
            missions.append(mission)
    return missions


def fetch_remotive(keywords: list[str]) -> list[dict[str, Any]]:
    """Remotive public API, pre-filtered server-side on 'ai'."""
    resp = requests.get("https://remotive.com/api/remote-jobs",
                        params={"search": "ai"},
                        headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = resp.json().get("jobs", [])
    missions: list[dict[str, Any]] = []
    for job in jobs:
        tags = " ".join(job.get("tags") or [])
        mission = {
            "source": "remotive",
            "url": job.get("url"),
            "title": job.get("title"),
            "company": job.get("company_name"),
            "location": job.get("candidate_required_location") or "Remote",
            "remote_policy": "remote",
            "language": "en",
            "engagement": ("contract"
                           if (job.get("job_type") or "") == "contract"
                           else detect_engagement(job.get("title"),
                                                  job.get("description"))),
            "rate": job.get("salary") or None,
            "description": strip_html(job.get("description") or "")[:5000],
            "stack": json.dumps(job.get("tags") or [], ensure_ascii=False),
        }
        if matches_keywords(mission, keywords, extra=tags):
            missions.append(mission)
    return missions


def fetch_weworkremotely(keywords: list[str]) -> list[dict[str, Any]]:
    """WeWorkRemotely programming-jobs RSS feed (xml.etree)."""
    resp = requests.get(
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    missions: list[dict[str, Any]] = []
    for item in root.iter("item"):
        raw_title = (item.findtext("title") or "").strip()
        # WWR titles look like "Company: Job Title"
        company, _, title = raw_title.partition(":")
        if not title:
            title, company = raw_title, ""
        description = strip_html(item.findtext("description") or "")
        region = (item.findtext("region") or "").strip()
        mission = {
            "source": "weworkremotely",
            "url": (item.findtext("link") or "").strip(),
            "title": title.strip(),
            "company": company.strip(),
            "location": region or "Remote",
            "remote_policy": "remote",
            "language": "en",
            "engagement": detect_engagement(raw_title, description),
            "rate": None,
            "description": description[:5000],
            "stack": json.dumps([], ensure_ascii=False),
        }
        if matches_keywords(mission, keywords):
            missions.append(mission)
    return missions


# TODO: Hacker News "Who is hiring" — fetch the latest monthly thread via the
# Algolia HN API (https://hn.algolia.com/api/v1/search?query=who%20is%20hiring),
# then pull top-level comments (item endpoint), parse "REMOTE" markers and
# keyword-match. Skipped for now per plan.


SOURCES: dict[str, Callable[[list[str]], list[dict[str, Any]]]] = {
    "remoteok": fetch_remoteok,
    "remotive": fetch_remotive,
    "weworkremotely": fetch_weworkremotely,
}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fetch_boards.py",
        description="Fetch remote-job boards, filter on AI/software keywords, "
                    "upsert into data/prospector.db")
    parser.add_argument("--dry-run", action="store_true",
                        help="print missions as JSON instead of writing to DB")
    parser.add_argument("--limit", type=int,
                        help="max missions kept per source")
    parser.add_argument("--source", choices=sorted(SOURCES),
                        help="fetch only this source")
    parser.add_argument("--keywords", nargs="+",
                        help="override keywords (default: config/targets.yaml "
                             "sources.boards.keywords, else built-ins)")
    args = parser.parse_args(argv)

    keywords = ([k.lower() for k in args.keywords] if args.keywords
                else load_keywords())
    selected = {args.source: SOURCES[args.source]} if args.source else SOURCES

    summary: dict[str, Any] = {"keywords": keywords, "sources": {}}
    for name, fetcher in selected.items():
        started = db.now_iso()
        errors = ""
        missions: list[dict[str, Any]] = []
        try:
            missions = fetcher(keywords)
        except Exception as exc:  # one source failing must not kill the run
            errors = f"{type(exc).__name__}: {exc}"
        if args.limit:
            missions = missions[: args.limit]

        if args.dry_run:
            summary["sources"][name] = {
                "found": len(missions),
                "errors": errors or None,
                "missions": missions,
            }
        else:
            counts = db.upsert_missions(missions) if missions else \
                {"inserted": 0, "skipped": 0}
            db.log_run(name, found=len(missions), new=counts["inserted"],
                       errors=errors, started_at=started)
            summary["sources"][name] = {
                "found": len(missions),
                "inserted": counts["inserted"],
                "skipped": counts["skipped"],
                "errors": errors or None,
            }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    any_ok = any(not s.get("errors") for s in summary["sources"].values())
    return 0 if any_ok else 1


if __name__ == "__main__":
    sys.exit(main())
