"""Render the 4 CV HTML variants to PDF in assets\\cv\\.

Run with:  venv\\Scripts\\python.exe scripts\\render_cv.py [--variant fr_short ...] [--force-playwright]

Inputs (may not exist yet — missing variants are skipped with a warning):
  cv\\fr_short\\index.html, cv\\fr_full\\index.html,
  cv\\en_short\\index.html, cv\\en_full\\index.html
Outputs: assets\\cv\\cv_<variant>.pdf

Strategy: Microsoft Edge headless print-to-pdf first (no extra install);
fallback to Playwright chromium (requires: venv\\Scripts\\playwright install chromium).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ROOT = Path(__file__).resolve().parent.parent
CV_DIR = ROOT / "cv"
OUT_DIR = ROOT / "assets" / "cv"

VARIANTS = ("fr_short", "fr_full", "en_short", "en_full")

EDGE_LOCATIONS = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)

MIN_PDF_BYTES = 10 * 1024  # a real CV PDF should exceed 10KB


def find_edge() -> Optional[Path]:
    for candidate in EDGE_LOCATIONS:
        if candidate.exists():
            return candidate
    return None


def pdf_ok(path: Path) -> bool:
    return path.exists() and path.stat().st_size > MIN_PDF_BYTES


def render_with_edge(edge: Path, html_file: Path, out_pdf: Path) -> bool:
    """Edge headless print-to-pdf, with a small retry/verify loop."""
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    if out_pdf.exists():
        out_pdf.unlink()
    file_url = html_file.resolve().as_uri()
    cmd = [
        str(edge), "--headless", "--disable-gpu", "--no-pdf-header-footer",
        f'--print-to-pdf={out_pdf.resolve()}', file_url,
    ]
    for attempt in range(2):
        try:
            subprocess.run(cmd, capture_output=True, timeout=90, check=False)
        except subprocess.TimeoutExpired:
            continue
        # Edge may return before the file is fully flushed — wait a bit.
        for _ in range(10):
            if pdf_ok(out_pdf):
                return True
            time.sleep(0.5)
        if attempt == 0:
            time.sleep(1.0)
    return pdf_ok(out_pdf)


def render_with_playwright(html_file: Path, out_pdf: Path) -> tuple[bool, str]:
    """Playwright chromium fallback. Returns (ok, error_message)."""
    try:
        from playwright.sync_api import sync_playwright, Error as PWError
    except ImportError:
        return False, "playwright not installed in the venv"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(html_file.resolve().as_uri(),
                      wait_until="networkidle")
            page.pdf(path=str(out_pdf), format="A4", print_background=True)
            browser.close()
    except PWError as exc:
        if "Executable doesn't exist" in str(exc):
            return False, ("playwright browsers not installed — run: "
                           r"venv\Scripts\playwright install chromium")
        return False, f"playwright error: {exc}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return pdf_ok(out_pdf), "" if pdf_ok(out_pdf) else "output PDF too small"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="render_cv.py",
        description="Print cv/<variant>/index.html to assets/cv/cv_<variant>.pdf "
                    "(Edge headless first, Playwright chromium fallback)")
    parser.add_argument("--variant", action="append", choices=VARIANTS,
                        help="render only this variant (repeatable; "
                             "default: all four)")
    parser.add_argument("--force-playwright", action="store_true",
                        help="skip Edge and use Playwright directly")
    args = parser.parse_args(argv)

    variants = args.variant or list(VARIANTS)
    edge = None if args.force_playwright else find_edge()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}
    for variant in variants:
        html_file = CV_DIR / variant / "index.html"
        out_pdf = OUT_DIR / f"cv_{variant}.pdf"
        if not html_file.exists():
            results[variant] = {"ok": False, "skipped": True,
                                "reason": f"missing input: {html_file}"}
            print(f"warning: skipping {variant} — {html_file} not found",
                  file=sys.stderr)
            continue

        ok = False
        error = ""
        engine = ""
        if edge:
            engine = "edge"
            ok = render_with_edge(edge, html_file, out_pdf)
            if not ok:
                error = "edge print-to-pdf failed or produced a tiny file"
        if not ok:
            engine = "playwright"
            ok, pw_error = render_with_playwright(html_file, out_pdf)
            if not ok:
                error = "; ".join(filter(None, [error, pw_error]))

        results[variant] = {
            "ok": ok,
            "engine": engine if ok else None,
            "output": str(out_pdf) if ok else None,
            "size_bytes": out_pdf.stat().st_size if ok else None,
            "error": error or None,
        }

    print(json.dumps(results, ensure_ascii=False, indent=2))
    rendered = [v for v, r in results.items() if r["ok"]]
    hard_failures = [v for v, r in results.items()
                     if not r["ok"] and not r.get("skipped")]
    return 1 if hard_failures else (0 if rendered or results else 0)


if __name__ == "__main__":
    sys.exit(main())
