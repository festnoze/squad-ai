"""One-time manual login into freelance platforms with a persistent profile.

Run with:  venv\\Scripts\\python.exe scripts\\login_setup.py --site malt

Opens a headed Playwright chromium using the persistent profile at
Prospector\\browser_profile\\ and navigates to the chosen site. Log in
manually, then simply close the browser window — cookies/session stay in the
profile and the scout agents reuse them.

If Playwright browsers are missing, run:
  venv\\Scripts\\playwright install chromium
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / "browser_profile"

SITES: dict[str, str] = {
    "malt": "https://www.malt.fr/signin",
    "linkedin": "https://www.linkedin.com/login",
    "upwork": "https://www.upwork.com/ab/account-security/login",
    "comet": "https://app.comet.co/",
    "freework": "https://www.free-work.com/fr/tech-it",
    "lehibou": "https://www.lehibou.com/connexion",
    "wttj": "https://www.welcometothejungle.com/fr/signin",
    "contra": "https://contra.com/login",
}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="login_setup.py",
        description="Open a headed chromium with the persistent "
                    "browser_profile/ so you can log in to a platform once")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--site", choices=sorted(SITES),
                       help="known platform to open")
    group.add_argument("--url", help="arbitrary URL to open")
    args = parser.parse_args(argv)

    url = args.url or SITES[args.site]

    try:
        from playwright.sync_api import sync_playwright, Error as PWError
    except ImportError:
        print("playwright is not installed in this venv. Run: "
              r"venv\Scripts\python.exe -m pip install playwright")
        return 1

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Opening {url}")
    print(f"Persistent profile: {PROFILE_DIR}")
    print("=> Log in manually in the window, then CLOSE the browser window.")
    print("   Your session stays saved in the profile for the scout agents.")

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                headless=False,
                viewport=None,
                args=["--start-maximized"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url)
            # Block until the user closes the window/context.
            try:
                page.wait_for_event("close", timeout=0)
            except PWError:
                pass  # context closed by the user — that's the happy path
            try:
                context.close()
            except PWError:
                pass
    except PWError as exc:
        if "Executable doesn't exist" in str(exc):
            print("Playwright browsers are not installed. Run:")
            print(r"  venv\Scripts\playwright install chromium")
            return 1
        print(f"Playwright error: {exc}")
        return 1

    print("Done. Session persisted in browser_profile\\.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
