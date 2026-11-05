"""Browser half of the B5 oracle: UX-01 to UX-07 driven in a real headless browser.

The bench annex fixes the API, not the interface: no URL but "/", no selector, no wording.
The driver therefore acts like a user who reads French. It finds fields by their type and
visible label (password, e-mail, search, a title next to a description), and actions by
their role and the French verbs a support UI uses (Se connecter, Nouveau ticket, Réessayer,
Suivant, Recharger...). Data is created through the API of the annex, effects are checked
through it, and failures are injected with Playwright request routing (500, network loss,
a hung request, a lost answer, an inverted pair of answers).

Only behaviour that the specification fixes is checked; every check stops at the X part of
its criterion, the visual (V) and review (R) parts stay with a human reviewer
(bench/oracles/B5_COVERAGE.md). A control the driver cannot find fails the check with the
step that blocked, so a reviewer can tell a missing feature from an unusual wording.

The checks run on a world of their own (fresh database, server process and accounts), after
the API phases, so they neither depend on nor disturb the API checks.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote_plus, urlparse

from bench import browser
from bench.oracle import Check, Product
from bench.oracles.B5 import ADMIN_EMAIL, Actor, Fail, World, attempt, expect

UX_IDS = [f"UX-{i:02d}" for i in range(1, 8)]
WAIT_S = 10.0
PROBE_S = 15.0  # how long "/" may take to show its login form before every UX check is blocked
TIMEOUT_LIMIT_S = 15.0  # specification section 6: frontend HTTP timeout of 15 s at most

LOGIN = re.compile(r"connexion|connecter", re.I)
LOGOUT = re.compile(r"d[ée]connexion|d[ée]connecter", re.I)
CREATE_TICKET = re.compile(r"(nouveau|nouvelle|cr[ée]er|ouvrir|ajouter|signaler)\b.{0,25}(ticket|demande)", re.I)
CREATE = re.compile(r"^\W*(nouveau|nouvelle|cr[ée]er|ajouter)\b", re.I)
SUBMIT = re.compile(r"cr[ée]er|envoyer|valider|soumettre|enregistrer|publier|ajouter", re.I)
RETRY = re.compile(r"r[ée]essayer|recharger|relancer|reprendre|actualiser|rafra[îi]chir", re.I)
CLOSE = re.compile(r"annuler|fermer", re.I)
NEXT_PAGE = re.compile(r"suivant|suivante|^\W*[›»>]\W*$", re.I)
LIST_NAV = re.compile(r"tickets|demandes|file d|accueil", re.I)
ACCOUNTS = re.compile(r"comptes|utilisateurs|administration", re.I)
SAVE = re.compile(r"enregistrer|appliquer|mettre à jour|valider|sauvegarder", re.I)
EMAIL_LABEL = re.compile(r"e-?mail|courriel|identifiant", re.I)
TITLE_LABEL = re.compile(r"titre|sujet|objet", re.I)
SEARCH_LABEL = re.compile(r"recherch|cherch", re.I)
PRIORITY_NAMES = {"low": "basse|faible", "normal": "normale|moyenne", "high": "haute|élevée|urgente"}

EMAIL_CSS = ("input[type=email], input[autocomplete=username], input[autocomplete=email], "
             "input[name*=mail i], input[id*=mail i]")
TEXT_INPUT = "input:not([type]), input[type=text]"
DIALOG = "[role=dialog], [role=alertdialog], dialog[open]"

# Journal of every text the page inserts in its DOM (transient displays included), and no
# CSS motion, so that focus styles are read without waiting for transitions.
INIT_SCRIPT = """(() => {
  const send = (text) => { if (text && text.trim() && window.__benchSeen) window.__benchSeen(text); };
  new MutationObserver((records) => {
    const parts = [];
    for (const record of records) {
      if (record.type === "characterData") parts.push(record.target.nodeValue || "");
      record.addedNodes.forEach((node) => parts.push(node.textContent || ""));
    }
    send(parts.join("\\n"));
  }).observe(document, { subtree: true, childList: true, characterData: true });
  document.addEventListener("DOMContentLoaded", () => {
    const style = document.createElement("style");
    style.textContent = "*, *::before, *::after { transition: none !important; animation: none !important; }";
    document.head.append(style);
  });
})();"""

# Style of the focused element, and of the previously focused one now that it lost the focus.
FOCUS_JS = """(previous) => {
  const sig = (el) => {
    const s = getComputedStyle(el);
    return [s.outlineStyle, s.outlineWidth, s.outlineColor, s.boxShadow, s.borderTopColor,
            s.borderBottomColor, s.backgroundColor, s.color, s.textDecorationLine].join("|");
  };
  const out = { blurred: null, focused: null };
  if (previous) {
    const el = document.querySelector(`[data-bench-focus="${previous}"]`);
    if (el) out.blurred = sig(el);
  }
  const el = document.activeElement;
  if (el && el !== document.body && el !== document.documentElement) {
    window.__benchFocus = (window.__benchFocus || 0) + 1;
    el.setAttribute("data-bench-focus", String(window.__benchFocus));
    const name = el.getAttribute("aria-label") || el.id || el.getAttribute("name") || el.textContent || "";
    out.focused = { key: String(window.__benchFocus), sig: sig(el),
                    name: `${el.tagName.toLowerCase()} ${name.trim()}`.slice(0, 50) };
  }
  return out;
}"""

UNLABELLED_JS = """(root) => {
  const shown = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
    && getComputedStyle(el).visibility !== "hidden";
  const out = [];
  for (const el of (root || document).querySelectorAll("input, select, textarea")) {
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (!shown(el) || ["hidden", "submit", "button", "reset", "image"].includes(type)) continue;
    const labels = [...(el.labels || [])].filter((l) => shown(l) && l.innerText.trim());
    const named = (el.getAttribute("aria-labelledby") || "").split(/\\s+/).filter(Boolean)
      .map((id) => document.getElementById(id)).filter((n) => n && shown(n) && n.innerText.trim());
    if (!labels.length && !named.length) out.push(`${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}`);
  }
  return out;
}"""

FIELD_ERROR_JS = """(el) => {
  const ids = `${el.getAttribute("aria-describedby") || ""} ${el.getAttribute("aria-errormessage") || ""}`
    .split(/\\s+/).filter(Boolean);
  return {
    invalid: el.getAttribute("aria-invalid") === "true" || !!(el.validity && !el.validity.valid),
    described: ids.map((id) => (document.getElementById(id)?.innerText || "").trim()).join(" | "),
  };
}"""

OVERFLOW_JS = """() => {
  const doc = document.documentElement;
  const scrolls = (el) => { for (let n = el.parentElement; n; n = n.parentElement) {
    if (/(auto|scroll)/.test(getComputedStyle(n).overflowX)) return true; } return false; };
  const cut = [];
  for (const el of document.querySelectorAll("button, a[href], input, select, textarea")) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height || scrolls(el)) continue;
    const partly = (r.left < -1 && r.right > 0) || (r.right > doc.clientWidth + 1 && r.left < doc.clientWidth);
    if (partly) cut.push((el.innerText || el.id || el.tagName).trim().slice(0, 30));  // skip links sit fully off screen
  }
  const wide = [...document.body.querySelectorAll("*")].filter((el) => el.scrollWidth > el.clientWidth + 1
    && el.clientWidth > 0 && getComputedStyle(el).overflowX === "visible" && !scrolls(el));
  const deepest = wide.filter((el) => !wide.some((other) => other !== el && el.contains(other)))
    .map((el) => `${el.tagName.toLowerCase()} "${(el.innerText || "").replace(/\\s+/g, " ").trim().slice(0, 25)}"`);
  return { width: doc.scrollWidth, viewport: doc.clientWidth, cut, wide: deepest.slice(0, 2) };
}"""

PRIORITY_JS = """() => {
  const want = /^(low|normal|high)$|basse|faible|normale|moyenne|haute|élevée|urgente/i;
  for (const el of document.querySelectorAll("select")) {
    if (!(el.offsetWidth || el.offsetHeight) || el.disabled) continue;
    const options = [...el.options];
    if (options.some((o) => o.value === "")) continue;  // a filter ("Toutes"), not a ticket field
    if (options.filter((o) => want.test(o.value) || want.test(o.textContent)).length < 3) continue;
    document.querySelectorAll("[data-bench-priority]").forEach((n) => n.removeAttribute("data-bench-priority"));
    el.setAttribute("data-bench-priority", "1");
    return true;
  }
  return false;
}"""


def _report(problems: list[str]) -> None:
    expect(not problems, "; ".join(problems[:5]) + (f" (+{len(problems) - 5})" if len(problems) > 5 else ""))


def _is_list(url: str) -> bool:
    return urlparse(url).path == "/api/tickets"


def _q(url: str) -> str:
    return parse_qs(urlparse(url).query).get("q", [""])[-1]


def _release(held: list) -> None:
    """Let held requests go on to the server. `fallback` never fails, even for a request the
    page already cancelled, so no route is left pending when the context closes."""
    for route in held:
        try:
            route.fallback()
        except Exception:  # already handled
            pass


def _titled(w: World, actor: Actor, title: str) -> list[dict]:
    """The actor's tickets with exactly this title, read through the API."""
    return [t for t in w.items(actor, "/api/tickets") if t.get("title") == title]


# --------------------------------------------------------------------------- driver


@dataclass
class Call:
    """One API request seen by the page, with its outcome once known."""

    method: str
    path: str
    query: dict[str, str]
    body: object
    status: int | None = None
    failed: bool = False

    @property
    def done(self) -> bool:
        return self.status is not None or self.failed


class Session:
    """One browser context (cookies, storage) and its page, with a journal of API calls."""

    def __init__(self, context, page, seen: list[str]) -> None:
        self.context, self.page, self.seen = context, page, seen
        self.calls: list[Call] = []
        self.focus_log: list[tuple[str, bool]] = []  # (element, its style changed with the focus)
        self._by_request: dict[int, Call] = {}
        self._focused: dict | None = None
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_failed)

    # -- journal
    def _on_request(self, request) -> None:
        url = urlparse(request.url)
        if not url.path.startswith("/api/"):
            return
        try:
            body = request.post_data_json
        except Exception:  # a body that is not JSON
            body = request.post_data
        call = Call(request.method, url.path, {k: v[-1] for k, v in parse_qs(url.query).items()}, body)
        self._by_request[id(request)] = call
        self.calls.append(call)

    def _on_response(self, response) -> None:
        call = self._by_request.get(id(response.request))
        if call is not None:
            call.status = response.status

    def _on_failed(self, request) -> None:
        call = self._by_request.get(id(request))
        if call is not None:
            call.failed = True

    def mark(self) -> int:
        return len(self.calls)

    def posts(self, since: int = 0) -> list[Call]:
        return [c for c in self.calls[since:] if c.method == "POST" and c.path == "/api/tickets"]

    # -- waiting
    def until(self, predicate: Callable[[], object], what: str, timeout_s: float = WAIT_S) -> object:
        """Poll ``predicate`` (letting the page run) until it is truthy; Fail(what) at the deadline."""
        deadline = time.monotonic() + timeout_s
        while True:
            value = predicate()
            if value:
                return value
            if time.monotonic() > deadline:
                raise Fail(what)
            self.page.wait_for_timeout(100)

    def call(self, method: str, path: str | re.Pattern, *, since: int = 0, what: str,
             where: Callable[[Call], bool] | None = None, timeout_s: float = WAIT_S) -> Call:
        """The first finished API call since ``since`` matching method, path and ``where``."""
        def matches(c: Call) -> bool:
            same = c.path == path if isinstance(path, str) else bool(path.fullmatch(c.path))
            return c.method == method and same and c.done and (where is None or where(c))

        return self.until(lambda: next((c for c in self.calls[since:] if matches(c)), None), what, timeout_s)

    def visible(self, *locators, what: str, timeout_s: float = WAIT_S):
        """The first visible match of the first locator (in order of preference) that has one."""
        def first():
            for locator in locators:
                shown = locator.filter(visible=True)
                if shown.count():
                    return [shown.first]
            return None

        return self.until(first, what, timeout_s)[0]

    def shown(self, locator) -> bool:
        return locator.filter(visible=True).count() > 0

    def control(self, name: re.Pattern, scope=None):
        scope = scope or self.page
        return scope.get_by_role("button", name=name).or_(scope.get_by_role("link", name=name))

    # -- reading
    def text(self) -> str:
        return self.page.locator("body").inner_text()

    def has_text(self, text: str) -> bool:
        return text.casefold() in self.text().casefold()

    def wait_text(self, text: str, what: str, timeout_s: float = WAIT_S) -> None:
        self.until(lambda: self.has_text(text), what, timeout_s)

    def ever_seen(self) -> str:
        return "\n".join(self.seen).casefold()

    def unlabelled(self, scope=None) -> list[str]:
        if scope is None:
            return self.page.evaluate(UNLABELLED_JS, None)
        return scope.evaluate(UNLABELLED_JS)

    def password(self):
        return self.page.locator("input[type=password]")

    # -- keyboard
    def tab(self, shift: bool = False) -> None:
        """Press Tab and record whether the element that lost the focus showed it visibly."""
        self.page.keyboard.press("Shift+Tab" if shift else "Tab")
        previous = self._focused
        info = self.page.evaluate(FOCUS_JS, previous["key"] if previous else None)
        if previous and info["blurred"] is not None:
            self.focus_log.append((previous["name"], info["blurred"] != previous["sig"]))
        self._focused = info["focused"]

    def is_focused(self, locator) -> bool:
        return locator.count() > 0 and locator.first.evaluate("el => el === document.activeElement")

    def tab_to(self, locator, what: str, presses: int = 15) -> None:
        for _ in range(presses):
            if self.is_focused(locator):
                return
            self.tab()
        expect(self.is_focused(locator), what)

    # -- user actions
    def home(self) -> None:
        self.page.goto("/", wait_until="domcontentloaded")

    def email_field(self):
        return self.visible(self.page.locator(EMAIL_CSS), self.page.get_by_label(EMAIL_LABEL),
                            what="login form: no e-mail field (type email, autocomplete username or an e-mail label)",
                            timeout_s=3)

    def submit_of(self, scope, name: re.Pattern):
        """The submit button of a form (or of the closest form around ``scope``)."""
        form = scope.locator("xpath=ancestor-or-self::form[1]")
        box = form if form.count() else scope
        for css in ("button[type=submit], input[type=submit]", "button:not([type])"):
            found = box.locator(css).filter(visible=True)
            if found.count():
                return found.first
        return self.visible(self.control(name, box if form.count() else None), what="the form has no submit button",
                            timeout_s=3)

    def login(self, actor: Actor) -> None:
        password = self.visible(self.password(), what="no login form (password field) on the page", timeout_s=15)
        email = self.email_field()
        email.fill(actor.email)
        password.fill(actor.password)
        mark = self.mark()
        self.submit_of(password, LOGIN).click()
        call = self.call("POST", "/api/auth/login", since=mark, what="the login form sends no POST /api/auth/login")
        expect(call.status == 200, f"login of {actor.email} through the UI -> {call.status}")
        self.until(lambda: not self.shown(self.password()), "the login form stays on screen after a successful login")

    def show_list(self, title: str, what: str) -> None:
        """Wait for ``title`` in the ticket list. When the app lands elsewhere (a dashboard, the
        route of the previous account), follow its ticket list navigation, as a user would."""
        try:
            self.wait_text(title, what, timeout_s=4)
            return
        except Fail:
            pass
        self._list_navigation()
        self.wait_text(title, what)

    def list_call(self) -> Call:
        """The ticket list request after login, following the list navigation if needed."""
        try:
            return self.call("GET", "/api/tickets", what="", timeout_s=4)
        except Fail:
            self._list_navigation()
            return self.call("GET", "/api/tickets", what="the ticket list is never requested after login")

    def _list_navigation(self) -> None:
        navigation = self.control(LIST_NAV).filter(visible=True)
        if navigation.count():
            navigation.first.click()

    def logout(self) -> None:
        self.visible(self.control(LOGOUT), what="no logout control (Se déconnecter, Déconnexion)").click()
        self.visible(self.password(), what="after logout the login form does not come back")

    def creation_form(self, *, open_it: bool = True):
        """(box, title, description, submit) of the visible ticket creation form."""
        def found():
            for area in self.page.locator("textarea").filter(visible=True).all():
                box = area.locator(f"xpath=ancestor::*[self::form or @role='dialog' or self::dialog][1]")
                if box.count() and box.locator(TEXT_INPUT).filter(visible=True).count():
                    return box.first, area
            return None

        hit = found()
        if hit is None:
            if open_it:
                self.opener().click()
            hit = self.until(found, "the creation control opens no form with a title and a description")
        box, description = hit
        title = self.visible(box.get_by_label(TITLE_LABEL).and_(box.locator(TEXT_INPUT)), box.locator(TEXT_INPUT),
                             what="creation form: no title field", timeout_s=3)
        return box, title, description, self.submit_of(description, SUBMIT)

    def opener(self):
        return self.visible(self.control(CREATE_TICKET), self.control(CREATE),
                            what="no control to create a ticket (Nouveau ticket, Créer un ticket...)")

    def dismiss(self) -> None:
        """Close an open creation form or dialog (Escape, then Annuler / Fermer)."""
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(300)
        if self.shown(self.page.locator(DIALOG)):
            dialog = self.page.locator(DIALOG).filter(visible=True).first
            self.visible(self.control(CLOSE, dialog), what="the creation dialog cannot be closed", timeout_s=3).click()
            self.until(lambda: not self.shown(self.page.locator(DIALOG)), "the creation dialog stays open")

    def create_ticket(self, title: str, description: str) -> Call:
        _, title_field, description_field, submit = self.creation_form()
        title_field.fill(title)
        description_field.fill(description)
        mark = self.mark()
        submit.click()
        return self.call("POST", "/api/tickets", since=mark, what="creation: no POST /api/tickets sent", timeout_s=20)

    def open_ticket(self, title: str, tid: str, *, since: int | None = None) -> None:
        """Click the ticket in the list; its detail must be fetched (GET /api/tickets/{id}...)."""
        mark = self.mark() if since is None else since
        name = re.compile(re.escape(title[:60]), re.I)
        target = self.visible(self.page.get_by_role("link", name=name), self.page.get_by_role("button", name=name),
                              self.page.get_by_role("row", name=name), self.page.get_by_text(name),
                              what=f"the ticket {title[:40]!r} is not listed")
        target.click()
        self.call("GET", re.compile(rf"/api/tickets/{re.escape(tid)}(/.*)?"), since=mark,
                  what="opening a ticket from the list fetches no detail (GET /api/tickets/{id})")

    def overflow(self, label: str, problems: list[str]) -> None:
        found = self.page.evaluate(OVERFLOW_JS)
        if found["width"] > found["viewport"] + 1:
            culprit = f" (content overflowing: {', '.join(found['wide'])})" if found["wide"] else ""
            problems.append(f"{label}: page {found['width']} px wide in a {found['viewport']} px viewport{culprit}")
        if found["cut"]:
            problems.append(f"{label}: controls cut off by the viewport: {found['cut'][:3]}")


class Ui:
    """The browser and the product's origin; one isolated session per scenario."""

    def __init__(self, engine: browser.Engine, origin: str) -> None:
        self.engine, self.origin = engine, origin
        self.tag = uuid.uuid4().hex[:6]

    @property
    def name(self) -> str:
        return self.engine.name

    @contextmanager
    def session(self, width: int = 1280, height: int = 800) -> Iterator[Session]:
        context = self.engine.browser.new_context(base_url=self.origin, locale="fr-FR",
                                                  viewport={"width": width, "height": height})
        context.set_default_timeout(WAIT_S * 1000)
        seen: list[str] = []

        def record(text: str) -> None:  # Playwright needs a plain function, not a builtin method
            seen.append(text)

        context.expose_function("__benchSeen", record)
        context.add_init_script(script=INIT_SCRIPT)
        page = context.new_page()
        try:
            yield Session(context, page, seen)
        finally:
            try:
                page.unroute_all(behavior="ignoreErrors")  # requests held by a check die quietly
                context.close()
            except Exception:  # a page already gone must not hide the check's own result
                pass

    def probe(self) -> str:
        """"" when "/" shows a login form, else why every UX check is blocked."""
        try:
            with self.session() as s:
                s.home()
                s.visible(s.password(), what=f"GET / shows no login form (password field) within {PROBE_S:.0f} s",
                          timeout_s=PROBE_S)
        except Fail as exc:
            return f"blocked: {exc}"
        except Exception as exc:
            return f"blocked: {type(exc).__name__}: {exc}"
        return ""


# --------------------------------------------------------------------------- UX checks


def ux_01(w: World, ui: Ui) -> str:
    """Login, list, creation and detail from "/" only; each role reaches its own view."""
    client = w.add_user("ux1", "client")
    existing = f"Ticket existant UX-01 {ui.tag}"
    w.ticket(client, title=existing)
    title = f"Création UX-01 {ui.tag}"
    description = f"Description du ticket UX-01 créé dans le navigateur {ui.tag}."
    with ui.session() as s:
        s.home()
        s.login(client)
        s.show_list(existing, "client: its existing ticket is not listed after login")
        expect(not s.shown(s.control(ACCOUNTS)), "client: an accounts navigation is offered to a client")
        mark = s.mark()
        created = s.create_ticket(title, description)
        expect(created.status == 201, f"client: creating a ticket through the UI -> {created.status}")
        s.wait_text(title, "client: the new ticket is not shown after its creation (no feedback)")
        found = _titled(w, client, title)
        expect(len(found) == 1, f"client: {len(found)} tickets titled {title!r} after one creation")
        s.open_ticket(title, str(found[0]["id"]), since=mark)
        s.wait_text(description, "client: the ticket detail does not show the description")
    with ui.session() as s:
        s.home()
        s.login(w.staff)
        s.show_list(existing, "agent: the team queue does not show the client's ticket")
    with ui.session() as s:
        s.home()
        s.login(w.admin)
        s.visible(s.control(ACCOUNTS), what="admin: no navigation to the accounts (Comptes, Utilisateurs, "
                  "Administration)").click()
        s.wait_text(client.email, "admin: the accounts view does not list the accounts")
    return ui.name


def _retries(s: Session) -> int:
    return s.control(RETRY).filter(visible=True).count()


def _error_shown(s: Session, baseline: int) -> bool:
    """A retry control appeared (beyond the ones the healthy page already shows, if any)."""
    return _retries(s) > baseline or (baseline > 0 and s.shown(s.page.locator("[role=alert]")))


def _failing_list(s: Session, label: str, handler: Callable, states: dict[str, str], baseline: int) -> None:
    """The list fails (500 or network): an error with a retry control, then a real recovery."""
    s.page.route(_is_list, handler)
    try:
        s.page.reload(wait_until="domcontentloaded")
        s.until(lambda: _error_shown(s, baseline), f"{label}: no error with a retry control (Réessayer, Recharger...)")
        text = s.text()
        expect(text != states["empty"], f"{label}: the error state looks exactly like the empty list")
        states[label] = text
    finally:
        s.page.unroute(_is_list, handler)
    mark = s.mark()
    s.control(RETRY).filter(visible=True).first.click()
    s.call("GET", "/api/tickets", since=mark, where=lambda c: c.status == 200,
           what=f"{label}: the retry control does not reload the list")
    s.until(lambda: _retries(s) <= baseline, f"{label}: the error stays on screen after a successful retry")


def _hung_list(s: Session, states: dict[str, str], baseline: int) -> None:
    """A list request that never answers: a loading state, then an error within 15 s."""
    held: list = []

    def hold(route) -> None:
        if route.request.method != "GET":
            route.fallback()
            return
        held.append(route)

    s.page.route(_is_list, hold)
    try:
        s.page.reload(wait_until="domcontentloaded")
        s.until(lambda: held, "hung request: the list is not requested after a reload")
        s.page.wait_for_timeout(400)
        loading = s.text()
        expect(loading.strip(), "slow loading: blank screen while the list loads")
        errors = [text for key, text in states.items() if key != "empty"]
        expect(loading != states["empty"] and loading not in errors,
               "slow loading: the loading state is not distinct from the empty or error state")
        s.until(lambda: _error_shown(s, baseline), timeout_s=TIMEOUT_LIMIT_S + 3,
                what=f"hung request: no error and retry control {TIMEOUT_LIMIT_S + 3:.0f} s after the request "
                     "(frontend HTTP timeout of 15 s at most, no endless loading)")
    finally:
        s.page.unroute(_is_list, hold)
        _release(held)
    mark = s.mark()
    s.control(RETRY).filter(visible=True).first.click()
    s.call("GET", "/api/tickets", since=mark, where=lambda c: c.status == 200,
           what="hung request: the retry control does not reload the list")


def _lost_answer(w: World, s: Session, client: Actor, tag: str) -> None:
    """The creation reaches the server but its answer is lost: same draft, same UUID, one ticket."""
    title = f"Réponse perdue UX-02 {tag}"
    description = f"Ticket créé pendant une coupure réseau simulée {tag}."
    bodies: list[dict] = []

    def lose_first(route) -> None:
        if route.request.method != "POST":
            route.fallback()
            return
        bodies.append(route.request.post_data_json or {})
        if len(bodies) == 1:
            route.fetch()  # the server creates the ticket...
            route.abort("connectionreset")  # ...and its answer never reaches the page
        else:
            route.fallback()

    s.page.route(_is_list, lose_first)
    try:
        _, title_field, description_field, submit = s.creation_form()
        title_field.fill(title)
        description_field.fill(description)
        mark = s.mark()
        submit.click()
        s.until(lambda: s.posts(mark) and s.posts(mark)[0].done, "creation: no POST /api/tickets sent")
        s.page.wait_for_timeout(1000)
        kept = s.shown(title_field) and title_field.input_value() == title \
            and description_field.input_value() == description
        expect(kept, "after a lost answer the draft (title and description) is not kept in the form")
        if len(bodies) < 2:  # no automatic retry: the user submits the same draft again
            s.until(lambda: submit.is_enabled(), "after a lost answer the submit button stays disabled")
            submit.click()
        s.until(lambda: len(s.posts(mark)) >= 2 and s.posts(mark)[1].done, "the retried creation never completes",
                timeout_s=20)
    finally:
        s.page.unroute(_is_list, lose_first)
    first, second = bodies[0].get("client_request_id"), bodies[1].get("client_request_id")
    expect(first and first == second, "the retry of an uncertain creation sends a new client_request_id")
    found = _titled(w, client, title)
    expect(len(found) == 1, f"{len(found)} tickets after a retried creation whose answer was lost, expected 1")


def ux_02(w: World, ui: Ui) -> str:
    """Empty, error, network failure, slow and hung states are distinct and recoverable."""
    client = w.add_user("ux2", "client")  # no ticket: the first list is empty
    problems: list[str] = []
    with ui.session() as s:
        s.home()
        s.login(client)
        listed = s.list_call()
        expect(listed.status == 200, f"GET /api/tickets -> {listed.status}")
        s.page.wait_for_timeout(500)
        states = {"empty": s.text()}
        expect(states["empty"].strip(), "blank screen for an empty list")
        baseline = _retries(s)  # a permanent refresh button is allowed; an error must add to it

        def fail_500(route) -> None:
            if route.request.method != "GET":
                route.fallback()
                return
            route.fulfill(status=500, content_type="application/json",
                          body=json.dumps({"error": {"code": "INTERNAL", "message": "Panne simulée par le banc"}}))

        def cut(route) -> None:
            if route.request.method != "GET":
                route.fallback()
                return
            route.abort("internetdisconnected")

        steps: list[tuple[str, Callable[[], None]]] = [
            ("API 500", lambda: _failing_list(s, "API 500 on the list", fail_500, states, baseline)),
            ("network", lambda: _failing_list(s, "network failure on the list", cut, states, baseline)),
            ("lost answer", lambda: _lost_answer(w, s, client, ui.tag)),
            ("hung request", lambda: _hung_list(s, states, baseline)),
        ]
        for label, step in steps:
            try:
                step()
            except Exception as exc:  # each step is judged alone; the next one starts from a fresh page
                problems.append(str(exc) if isinstance(exc, Fail) else f"{label}: {type(exc).__name__}: {exc}")
                s.page.unroute_all(behavior="ignoreErrors")
                s.home()
    _report(problems)
    return ""


def ux_03(w: World, ui: Ui) -> str:
    """Keyboard login with visible focus, labelled fields, a trapped dialog, field errors."""
    client = w.add_user("ux3", "client")
    problems: list[str] = []
    note = ""
    with ui.session() as s:
        s.home()
        s.visible(s.password(), what="no login form (password field) on the page", timeout_s=15)
        missing = s.unlabelled()
        if missing:
            problems.append(f"login fields without a visible label: {missing}")
        s.tab_to(s.email_field(), "keyboard: Tab never reaches the e-mail field")
        s.page.keyboard.type(client.email)
        s.tab_to(s.password().filter(visible=True), "keyboard: Tab does not lead from the e-mail to the password")
        s.page.keyboard.type(client.password)
        mark = s.mark()
        s.page.keyboard.press("Enter")
        login = s.call("POST", "/api/auth/login", since=mark, what="keyboard: Enter in the password does not log in")
        expect(login.status == 200, f"keyboard login -> {login.status}")
        s.until(lambda: not s.shown(s.password()), "keyboard login: the login form stays on screen")
        for _ in range(6):
            s.tab()
        invisible = sorted({name for name, changed in s.focus_log if not changed})
        if invisible:
            problems.append(f"no visible focus indicator on: {invisible[:4]}")

        opener = s.opener()
        opener.focus()
        s.page.keyboard.press("Enter")
        box, title, description, submit = s.creation_form(open_it=False)
        missing = s.unlabelled(box)
        if missing:
            problems.append(f"creation fields without a visible label: {missing}")
        dialogs = s.page.locator(DIALOG).filter(visible=True)
        if not dialogs.count():
            note = "creation form in a panel, not a dialog: the modal part was not observed"
        else:
            dialog = dialogs.first
            inside = "el => el.contains(document.activeElement)"
            if not dialog.evaluate(inside):
                problems.append("dialog: the focus does not move into it when it opens")
            for shift in [False] * 10 + [True] * 4:
                s.page.keyboard.press("Shift+Tab" if shift else "Tab")
                if not dialog.evaluate(inside):
                    problems.append("dialog: Tab moves the focus out of the open dialog")
                    break
            s.page.keyboard.press("Escape")
            try:
                s.until(lambda: not s.shown(s.page.locator(DIALOG)), "dialog: Escape does not close it", 3)
                s.until(lambda: s.is_focused(opener), "dialog: the focus does not return to the control that "
                        "opened it", 3)
            except Fail as exc:
                problems.append(str(exc))
                s.dismiss()
            s.opener().click()
            box, title, description, submit = s.creation_form(open_it=False)
        before = title.evaluate(FIELD_ERROR_JS)
        title.fill("Abcd")
        description.fill(f"Description valide pour le contrôle UX-03 {ui.tag}.")
        mark = s.mark()
        submit.click()

        def flagged() -> bool:
            after = title.evaluate(FIELD_ERROR_JS)
            return after["invalid"] or (after["described"] and after["described"] != before["described"])

        try:
            s.until(flagged, "a 4 character title gets no error tied to its field (aria-invalid, "
                    "aria-describedby or native validation)", 5)
        except Fail as exc:
            problems.append(str(exc))
        if any(c.status == 201 for c in s.posts(mark)):
            problems.append("a 4 character title was accepted")
    _report(problems)
    return note


def ux_04(w: World, ui: Ui) -> str:
    """At 1280 and 390 px, with long words: no global horizontal overflow, no control cut off."""
    client = w.add_user("ux4", "client")
    title = "Anticonstitutionnellement" * 4  # 100 characters without a break opportunity
    description = f"Un mot très long : {'Intergouvernementalisation' * 12} et la fin du texte {ui.tag}."
    tid = w.ticket(client, title=title, description=description)
    problems: list[str] = []
    for width, height in ((1280, 800), (390, 844)):
        with ui.session(width, height) as s:
            s.home()
            s.visible(s.password(), what="no login form (password field) on the page", timeout_s=15)
            s.overflow(f"{width} px login", problems)
            s.login(client)
            s.show_list(title[:40], f"{width} px: the ticket with a long title is not listed")
            s.overflow(f"{width} px list", problems)
            s.open_ticket(title, tid)
            s.wait_text(description[:30], f"{width} px: the detail does not show the description")
            s.overflow(f"{width} px detail", problems)
    _report(problems)
    return ""


def ux_05(w: World, ui: Ui) -> str:
    """Switching accounts in one browser, and an expired session, expose nothing private."""
    alice, bob = w.add_user("ux5a", "client"), w.add_user("ux5b", "client")
    first = f"Dossier privé de ux5a {ui.tag}"
    second = f"Dossier de ux5b {ui.tag}"
    w.ticket(alice, title=first)
    w.ticket(bob, title=second)
    draft_title, draft_body = f"Brouillon ux5a {ui.tag}", f"Texte de brouillon jamais envoyé par ux5a {ui.tag}."
    private = [first, draft_title, draft_body, alice.email, ADMIN_EMAIL]
    with ui.session() as s:
        s.home()
        s.login(w.admin)
        s.visible(s.control(ACCOUNTS), what="admin: no navigation to the accounts").click()
        s.wait_text(alice.email, "admin: the accounts view does not list the accounts")
        admin_url = s.page.url
        s.logout()
        s.login(alice)
        s.show_list(first, "first client: its ticket is not listed")
        _, title, description, _ = s.creation_form()
        title.fill(draft_title)
        description.fill(draft_body)
        s.dismiss()
        s.logout()
        s.seen.clear()
        s.login(bob)
        s.show_list(second, "second client: its own ticket is not listed")
        _, title, description, _ = s.creation_form()
        expect(not title.input_value() and not description.input_value(),
               "the previous account's creation draft is offered to the next account")
        s.dismiss()
        s.page.goto(admin_url, wait_until="domcontentloaded")
        s.page.wait_for_timeout(2500)  # the client route renders, fetches and is refused
        leaks = [p for p in private if p.casefold() in s.ever_seen()]
        expect(not leaks, f"after a logout then another login (and on the admin route), the page showed {leaks}")
        stored = s.page.evaluate("() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)])")
        kept = [p for p in private[:3] if p in stored]
        expect(not kept, f"browser storage keeps the previous account's data: {kept}")
        s.home()
        s.show_list(second, "second client: its ticket is not listed again")
        s.context.clear_cookies()  # the session is gone, as after its 8 h expiry: the next call gets 401
        name = re.compile(re.escape(second), re.I)
        s.visible(s.page.get_by_role("link", name=name), s.page.get_by_role("button", name=name),
                  s.page.get_by_text(name), what="second client: its ticket is not clickable").click()
        s.visible(s.password(), what="expired session: an API call answered 401 does not bring the login form back")
        expect(not s.has_text(second), "expired session: private data stays on screen next to the login form")
    return ""


def ux_06(w: World, ui: Ui) -> str:
    """A late answer never replaces the current search; query and page live in the URL."""
    client = w.add_user("ux6", "client")
    for i in range(50):
        w.ticket(client, title=f"Ticket de charge {i:02d} {ui.tag}")
    alpha, bravo = f"Alpha {ui.tag}", f"Bravo {ui.tag}"
    w.ticket(client, title=f"{alpha} imprimante")
    w.ticket(client, title=f"{bravo} imprimante")
    problems: list[str] = []
    with ui.session() as s:
        s.home()
        s.login(client)
        s.show_list(f"{bravo} imprimante", "the ticket list is not shown after login")

        def search_field():
            return s.visible(s.page.get_by_role("searchbox"), s.page.get_by_label(SEARCH_LABEL),
                             s.page.get_by_placeholder(SEARCH_LABEL), what="no search field on the ticket list")

        held: list = []

        def hold_alpha(route) -> None:
            if route.request.method == "GET" and alpha.casefold() in _q(route.request.url).casefold():
                held.append(route)
            else:
                route.fallback()

        s.page.route(_is_list, hold_alpha)
        try:
            search = search_field()
            search.fill(alpha)
            search.press("Enter")
            s.until(lambda: held, "search: a query followed by Enter sends no GET /api/tickets?q=...")
            mark = s.mark()
            search.fill(bravo)
            search.press("Enter")
            s.call("GET", "/api/tickets", since=mark, where=lambda c: bravo.casefold() in c.query.get("q", "").casefold(),
                   what="search: the second query is never sent")
            s.wait_text(f"{bravo} imprimante", "search: the results of the current query are not shown")
        finally:
            s.page.unroute(_is_list, hold_alpha)
        _release(held)  # the first answer arrives last (unless the page cancelled it: also valid)
        s.page.wait_for_timeout(1500)
        if s.has_text(f"{alpha} imprimante") or not s.has_text(f"{bravo} imprimante"):
            problems.append("a late answer of a previous search replaced the results of the current one")

        if bravo.casefold() not in unquote_plus(s.page.url).casefold():
            problems.append(f"the search is not kept in the URL ({s.page.url})")
        mark = s.mark()
        s.page.reload(wait_until="domcontentloaded")
        s.call("GET", "/api/tickets", since=mark, what="reload: the list is not requested")
        s.page.wait_for_timeout(500)
        if not any(bravo.casefold() in c.query.get("q", "").casefold() for c in s.calls[mark:] if c.path == "/api/tickets"):
            problems.append("reload: the search is lost (no list request carries it)")

        mark = s.mark()
        search = search_field()
        search.fill("")
        search.press("Enter")
        s.call("GET", "/api/tickets", since=mark, where=lambda c: not c.query.get("q"),
               what="clearing the search sends no new list request")
        mark = s.mark()
        s.visible(s.control(NEXT_PAGE), what="no next page control on a list of 52 tickets").click()
        s.call("GET", "/api/tickets", since=mark, where=lambda c: c.query.get("page") == "2",
               what="the next page control does not request page 2")
        mark = s.mark()
        s.page.reload(wait_until="domcontentloaded")
        s.call("GET", "/api/tickets", since=mark, what="reload: the list is not requested")
        s.page.wait_for_timeout(500)
        if not any(c.query.get("page") == "2" for c in s.calls[mark:] if c.path == "/api/tickets"):
            problems.append("reload: the page number is lost")
        mark = s.mark()
        search = search_field()
        search.fill(f"charge {ui.tag}")
        search.press("Enter")
        changed = s.call("GET", "/api/tickets", since=mark, where=lambda c: "charge" in c.query.get("q", ""),
                         what="a new search sends no list request")
        if changed.query.get("page", "1") != "1":
            problems.append(f"a new search keeps page {changed.query.get('page')} instead of going back to page 1")
    _report(problems)
    return ""


def _priority(s: Session):
    s.until(lambda: s.page.evaluate(PRIORITY_JS), "staff: no priority selector (low, normal, high) on the detail")
    return s.page.locator("[data-bench-priority]")


def _choose(s: Session, level: str) -> str:
    """Select a priority level in the detail; returns the option value chosen."""
    select = _priority(s)
    value = select.evaluate("(el, [level, names]) => { const re = new RegExp(names, 'i');"
                            " const o = [...el.options].find((o) => o.value === level || re.test(o.textContent));"
                            " return o ? o.value : null; }", [level, PRIORITY_NAMES[level]])
    expect(value is not None, f"the priority selector has no {level} option")
    select.select_option(value=value)
    return value


def _save(s: Session, since: int) -> Call:
    """The PATCH sent by the change, clicking the form's save control when nothing is sent."""
    patch = re.compile(r"/api/tickets/[^/]+")
    try:
        return s.call("PATCH", patch, since=since, what="", timeout_s=2)
    except Fail:
        pass
    s.submit_of(_priority(s), SAVE).click()
    return s.call("PATCH", patch, since=since, what="changing the priority and saving sends no PATCH")


def ux_07(w: World, ui: Ui) -> str:
    """A double click creates one ticket; a 409 offers a reload, keeps the choice, never overwrites."""
    client = w.add_user("ux7", "client")
    title = f"Double clic UX-07 {ui.tag}"
    problems: list[str] = []
    with ui.session() as s:
        s.home()
        s.login(client)
        _, title_field, description_field, submit = s.creation_form()
        title_field.fill(title)
        description_field.fill(f"Ticket soumis par un double clic {ui.tag}.")
        box = submit.bounding_box()
        mark = s.mark()
        s.page.mouse.dblclick(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        s.until(lambda: s.posts(mark) and all(c.done for c in s.posts(mark)), "double click: no POST /api/tickets")
        s.page.wait_for_timeout(1500)
        count = len(_titled(w, client, title))
        if count != 1:
            problems.append(f"a double click on the creation button created {count} tickets")
    conflict = f"Conflit UX-07 {ui.tag}"
    tid = w.ticket(client, title=conflict)
    with ui.session() as s:
        s.home()
        s.login(w.staff)
        s.open_ticket(conflict, tid)
        _priority(s)
        other = w.call("PATCH", f"/api/tickets/{tid}", {"expected_version": w.version(tid), "priority": "high"},
                       actor=w.staff)
        expect(other.status == 200, f"the oracle's own concurrent change -> {other}")
        mark = s.mark()
        chosen = _choose(s, "low")
        patch = _save(s, mark)
        expect(patch.status == 409, f"saving over a stale version through the UI -> {patch.status}, expected 409")
        s.page.wait_for_timeout(2500)
        if len([c for c in s.calls[mark:] if c.method == "PATCH"]) > 1:
            problems.append("after the 409 the UI sends the change again by itself")
        if w.get(tid).get("priority") != "high":
            problems.append("the concurrent change was overwritten")
        if _priority(s).input_value() != chosen:
            problems.append("after the 409 the priority selector no longer shows the user's choice (draft not kept)")
        reload = s.visible(s.control(RETRY), what="after a 409 no control offers to reload the ticket")
        mark = s.mark()
        reload.click()
        s.call("GET", re.compile(rf"/api/tickets/{re.escape(tid)}"), since=mark,
               what="the reload control does not fetch the ticket again")
        s.page.wait_for_timeout(500)
        mark = s.mark()
        _choose(s, "low")
        again = _save(s, mark)
        if again.status != 200:
            problems.append(f"after the reload, saving the choice again -> {again.status} (form not reusable)")
    _report(problems)
    return ""


UX_CHECKS: list[tuple[str, Callable[[World, Ui], str]]] = [
    ("UX-01", ux_01), ("UX-02", ux_02), ("UX-03", ux_03), ("UX-04", ux_04),
    ("UX-05", ux_05), ("UX-06", ux_06), ("UX-07", ux_07),
]


def _all(detail: str) -> dict[str, Check]:
    return {cid: Check(cid, False, detail) for cid in UX_IDS}


def _setup_staff(w: World) -> str:
    try:
        w.add_user("camille", "agent")
    except Exception as exc:  # any surprise here blocks the UX checks, never the run
        return f"account setup: {exc}"
    return ""


def run(product: Product, work: Path) -> dict[str, Check]:
    """UX-01 to UX-07 on a world of their own: fresh database, server and accounts."""
    w = World(product, work / "ui.db")
    rc = w.bootstrap(credentials=True).returncode
    if rc != 0:
        return _all(f"not run: create-admin on the UI database -> rc={rc}")
    try:
        with w.server():
            reason = w.setup_admin() or _setup_staff(w)
            if reason:
                return _all(f"not run: {reason}")
            with browser.launch() as engine:
                ui = Ui(engine, w.api.origin)
                gate = ui.probe()
                if gate:
                    return _all(gate)
                out: dict[str, Check] = {}
                for cid, fn in UX_CHECKS:
                    failure, note = attempt(lambda world, fn=fn: fn(world, ui), w)
                    out[cid] = Check(cid, not failure, failure or note)
                return out
    except browser.BrowserUnavailable as exc:
        return _all(f"not run: {exc}")
    except RuntimeError as exc:
        return _all(f"not run: UI server: {exc}")
