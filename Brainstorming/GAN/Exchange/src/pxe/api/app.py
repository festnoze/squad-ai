"""The application factory of the replay API (CONTRACTS section 7.21).

:func:`create_app` is **the one factory**. It wires the four things the API is
made of and nothing else:

* a :class:`~pxe.store.db.Store` over ``runs_dir`` (built with
  :func:`~pxe.store.db.default_store_url` when the caller supplies none);
* the ``/api`` router of :mod:`pxe.api.routes`;
* the ``/ws/matches/{match_id}`` socket of :mod:`pxe.api.ws`;
* ``GET /replay/{match_id}``, the share link of T4.5, which serves the built UI
  bundle with no server side rendering and no session.

Two guarantees are enforced here rather than documented:

**Read only by construction.** No route in this application uses POST, PUT,
PATCH or DELETE, and a request that does, on any path, is refused with ``405``
before routing (CONTRACTS decision 33,
``test_api.py::test_api_exposes_no_mutating_verb``).

**One error shape.** Every 4xx and 5xx body is
``{"error": {"code": ..., "message": ..., "detail": {...}}}``, so
``web/src/api/client.ts`` throws one ``ApiError`` type built from that shape and
nothing else.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint

from pxe import ACTION_VERSION, ENGINE_VERSION, OBS_VERSION
from pxe.api.routes import (
    API_VERSION,
    ReplayService,
    build_router,
    iter_payload_models,
    sample_payloads,
)
from pxe.api.ws import build_ws_router
from pxe.errors import PxeError
from pxe.store.db import Store, default_store_url

__all__ = [
    "API_VERSION",
    "READ_ONLY_METHODS",
    "DEFAULT_CORS_ORIGINS",
    "create_app",
    "render_replay_api_markdown",
    "write_sample_fixtures",
    "payload_models",
    "repo_root",
]

#: The only HTTP methods this application answers. ``OPTIONS`` is kept for the
#: CORS preflight of the Vite dev server; everything else is a ``405``.
READ_ONLY_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})

#: Default CORS origins: the Vite dev server of section 7.25, so A24 can work
#: against a locally served API without editing an A22 file.
DEFAULT_CORS_ORIGINS: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

#: A Sphinx cross reference role in a model docstring, as the generated document
#: must not show it (``:class:`MatchDetail``` reads as noise to a TypeScript
#: developer, who wants ``MatchDetail``).
_ROLE_PATTERN: str = r":(?:class|func|data|mod|meth|attr):`~?([^`]+)`"

#: What a matched role collapses to: the referenced name, in code font.
_ROLE_REPLACEMENT: str = "`\\1`"


def repo_root() -> Path:
    """Return the repository root, the parent of ``src/`` and of ``web/``.

    Returns:
        ``<root>`` such that ``<root>/web/dist/index.html`` is the built UI
        bundle ``GET /replay/{match_id}`` serves.
    """
    return Path(__file__).resolve().parents[3]


def _error_response(status: int, code: str, message: str, **detail: Any) -> JSONResponse:
    """Render the one error body of section 7.21 rule 3."""
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "detail": dict(detail)}},
    )


def create_app(
    *,
    runs_dir: Path,
    store: Store | None = None,
    cors_origins: Sequence[str] = DEFAULT_CORS_ORIGINS,
) -> FastAPI:
    """Build the replay application.

    Args:
        runs_dir: The runs root holding ``runs/<match_id>/`` artefacts.
        store: The projection database. ``None`` builds one over
            :func:`~pxe.store.db.default_store_url` of ``runs_dir``.
        cors_origins: Allowed browser origins. The default is the Vite dev
            server of section 7.25.

    Returns:
        The configured :class:`~fastapi.FastAPI` application. It carries the
        service on ``app.state.replay_service`` so a caller can share the cache
        (``pxe api openapi --samples`` does).
    """
    resolved_runs = Path(runs_dir)
    resolved_store = store if store is not None else Store(url=default_store_url(resolved_runs), runs_dir=resolved_runs)
    resolved_store.init_schema()
    service = ReplayService(runs_dir=resolved_runs, store=resolved_store)

    app = FastAPI(
        title="pxe replay API",
        version=API_VERSION,
        summary="Read only replay of Prediction Exchange matches and tournaments.",
        description=(
            "Every payload is JSON with integer money in cents, integer prices in 1..99 and probabilities as "
            "*_ppm integers. The API recomputes no engine logic: every number comes from the journal, from the "
            "metrics projection or from the store. There is no POST, PUT, PATCH or DELETE anywhere."
        ),
        openapi_tags=[{"name": "replay", "description": "Read only replay routes (CONTRACTS section 7.21)."}],
    )
    app.state.replay_service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def aread_only_guard(request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Refuse every mutating verb, on every path, before routing.

        FastAPI answers ``405`` for a declared path reached with the wrong method
        and ``404`` for an undeclared one, so "the API exposes no mutating verb"
        would be true of the declared paths and invisible everywhere else. This
        guard makes the guarantee total and gives it the one error shape.
        ``OPTIONS`` stays allowed so the CORS preflight still works.

        Args:
            request: The incoming request.
            call_next: The rest of the stack.

        Returns:
            The downstream response, or the ``405`` body.
        """
        if request.method.upper() not in READ_ONLY_METHODS:
            return _error_response(
                405,
                "READ_ONLY_API",
                "the replay API exposes no mutating verb",
                method=request.method.upper(),
                path=request.url.path,
            )
        return await call_next(request)

    app.include_router(build_router(service))
    app.include_router(build_ws_router(service))
    _install_error_handlers(app)
    _install_share_page(app, service)
    return app


def _install_error_handlers(app: FastAPI) -> None:
    """Give every failure the one body shape of section 7.21 rule 3."""

    @app.exception_handler(HTTPException)
    async def ahttp_error(request: Request, exc: HTTPException) -> JSONResponse:
        """Render an ``HTTPException`` raised by a route or by FastAPI itself."""
        _ = request
        detail = exc.detail
        if isinstance(detail, Mapping):
            return _error_response(
                exc.status_code,
                str(detail.get("code", "HTTP_ERROR")),
                str(detail.get("message", "")),
                **dict(detail.get("detail", {})),
            )
        return _error_response(exc.status_code, _default_code(exc.status_code), str(detail))

    @app.exception_handler(RequestValidationError)
    async def avalidation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """A malformed query parameter is a ``400`` (section 7.21 rule 3)."""
        _ = request
        return _error_response(
            400,
            "INVALID_QUERY",
            "malformed query parameter",
            errors=[
                {
                    "loc": [str(part) for part in error.get("loc", ())],
                    "msg": str(error.get("msg", "")),
                    "type": str(error.get("type", "")),
                }
                for error in exc.errors()
            ],
        )

    @app.exception_handler(PxeError)
    async def apxe_error(request: Request, exc: PxeError) -> JSONResponse:
        """An engine level error that escaped a route is a ``500`` with its own code."""
        _ = request
        return _error_response(500, exc.code, str(exc))


def _default_code(status: int) -> str:
    """Map a bare HTTP status to the code the one error shape carries."""
    return {
        400: "INVALID_QUERY",
        404: "NOT_FOUND",
        405: "READ_ONLY_API",
        409: "INCOMPLETE_ARTEFACT",
    }.get(status, "SERVER_ERROR")


def _install_share_page(app: FastAPI, service: ReplayService) -> None:
    """Serve the T4.5 share link at ``GET /replay/{match_id}``."""

    @app.get("/replay/{match_id}", response_class=HTMLResponse, include_in_schema=True, tags=["replay"])
    def get_replay_page(match_id: str) -> HTMLResponse:
        """Serve ``web/dist/index.html`` for a recorded match.

        The page is a plain URL with no query string and no token: the
        application reads ``match_id`` from its own path (section 7.21). The
        match is looked up first, so a share link to a match this server cannot
        replay is a ``404`` rather than a blank application.

        Args:
            match_id: The match to open.

        Returns:
            The UI bundle, or a self contained read only fallback page when
            ``web/dist`` has not been built yet.
        """
        service.view(match_id)
        bundle = repo_root() / "web" / "dist" / "index.html"
        if bundle.exists():
            return HTMLResponse(content=bundle.read_text(encoding="utf-8"))
        return HTMLResponse(content=_fallback_share_page(match_id))


def _fallback_share_page(match_id: str) -> str:
    """Build the self contained page served when ``web/dist`` is absent.

    It references no external script, stylesheet, font or image, so the share
    link stays autonomous and read only (T4.5) even before A24's bundle exists,
    and ``test_api.py::test_share_page_is_self_contained`` asserts exactly that.

    Args:
        match_id: The match the link points at.

    Returns:
        A complete HTML document.
    """
    safe = match_id.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex">'
        f"<title>pxe replay {safe}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;line-height:1.5}"
        "code{background:#eee;padding:.1rem .3rem}</style></head><body>"
        f"<h1>Replay {safe}</h1>"
        "<p>This is a read only replay share link. The web bundle "
        "(<code>web/dist/index.html</code>) has not been built in this checkout, so the "
        "interactive view is unavailable; the data is served by the read only API.</p>"
        f"<p>Match payload: <code>/api/matches/{safe}</code></p>"
        f"<p>Tick payload: <code>/api/matches/{safe}/ticks/1</code></p>"
        f"<p>Live stream: <code>/ws/matches/{safe}?speed=1&amp;from_tick=1</code></p>"
        "</body></html>\n"
    )


# ---------------------------------------------------------------------------
# `pxe api openapi` support (section 7.22)
# ---------------------------------------------------------------------------
def render_replay_api_markdown(app: FastAPI) -> str:
    """Render ``docs/REPLAY_API.md`` from the real FastAPI schema.

    Section 7.21 requires the generated counterpart of its route table, and
    section 7.22 gives ``pxe api openapi`` the verb. Following ruling R34's
    precedent this function **returns a string** and the caller writes the
    file, so :mod:`pxe.api` keeps the section 2.7 filesystem ban.

    Args:
        app: The application, normally :func:`create_app`.

    Returns:
        The whole document.
    """
    schema = app.openapi()
    lines: list[str] = [
        "# Replay API",
        "",
        "**Generated by `pxe api openapi` from the real FastAPI schema. Do not edit by hand.**",
        "",
        f"Payload version `{API_VERSION}`, engine `{ENGINE_VERSION}`, observation `{OBS_VERSION}`,",
        f"action `{ACTION_VERSION}`.",
        "",
        "The API is read only: it declares no POST, PUT, PATCH or DELETE, and a request using one of",
        "those verbs is refused with `405` on every path (CONTRACTS decision 33). Money is integer",
        "cents, a price is an integer in `1..99`, a probability is a `*_ppm` integer and a duration is",
        "a number of ticks. Keys are `snake_case` on the wire and in `web/src/api/types.ts`.",
        "",
        "## Routes",
        "",
        "| Method | Path | Query | 200 body |",
        "|---|---|---|---|",
    ]
    lines.extend(_route_rows(schema))
    lines.extend(
        [
            "",
            "| WS | `/ws/matches/{match_id}` | `speed=1`, `from_tick=1` | see the frame table below |",
            "",
            "## Errors",
            "",
            "Every 4xx and 5xx body is one shape:",
            "",
            "```json",
            '{"error": {"code": "UNKNOWN_MATCH", "message": "no journal for that match id",',
            ' "detail": {"match_id": "m-election-1-01"}}}',
            "```",
            "",
            "`404` unknown match, tournament or tick. `400` a malformed query parameter (including a",
            "`q` longer than 200 characters). `409` an artefact that exists but is incomplete. `405`",
            "any mutating verb. `500` anything else.",
            "",
            "## WebSocket frames",
            "",
            "One JSON text frame per message, discriminated by `type`. `speed` is one of",
            "`1, 2, 4, 8, 16, 32, 64` ticks per second; any other value closes the socket with `4400`.",
            "The stream is a projection replay of a finished journal, never a live match: the server is",
            "the clock and a `tick` frame carries the whole `TickState`, so a client can resume from any",
            "tick with no state of its own.",
            "",
            "| Direction | `type` | Payload |",
            "|---|---|---|",
            "| server | `hello` | `{match_id, ticks_total, speed, from_tick, api_version, engine_version}` |",
            "| server | `snapshot` | `{tick, state: TickState}` |",
            "| server | `tick` | `{tick, state: TickState}` |",
            "| server | `highlight` | `{highlight: Highlight}`, immediately before its `tick` frame |",
            "| server | `ended` | `{final_tick, rankings, mm_pnl_cents, fees_collected_cents}` |",
            "| server | `error` | `{code, message}`, the socket stays open |",
            "| server | `pong` | `{t}`, echoing the `ping` |",
            "| client | `play` | `{}` |",
            "| client | `pause` | `{}` |",
            "| client | `seek` | `{tick}`, clamped, answered with one `snapshot` |",
            "| client | `speed` | `{speed}`, effective on the next tick |",
            "| client | `ping` | `{t}` |",
            "",
            "Close codes: `4404` unknown match, `4400` a bad `speed` or `from_tick`, `1011` server",
            "error. `from_tick` and `seek` accept `0` (the opening configuration) and `ticks_total + 1`",
            "(finalisation).",
            "",
            "## Derived fields",
            "",
            "The API recomputes no engine logic. Nine payload fields nonetheless have no single",
            "journalled number behind them, and each one is a regrouping of journalled values:",
            "",
            "| Field | How it is built |",
            "|---|---|",
            "| `MarketTick.bids` / `.asks` | resting quantity per price, folded from `OrderPlaced.qty`"
            " minus the `TradeExecuted.qty` that consumed it and dropped on `OrderCancelled`, snapshotted"
            " at the `MarkToMarket` of that tick. Checked against the journalled `best_bid`, `best_ask`,"
            " `bid_depth_qty` and `ask_depth_qty`. |",
            "| `MatchSeries.rank` | equity descending at each tick, ties sharing the lowest rank, broken"
            " for display by ascending `agent_id` (the finalisation step 18 display rule). |",
            "| `AgentInfo.kind` | `llm` when the seat ever produced an `AgentActionReceived` with"
            ' `source == "llm"`, `scripted` otherwise. `MatchStarted.agents` carries no `kind`. |',
            "| `AgentInfo.colour_index` | seat number minus one, `A1` is `0`. `MM` is out of ranking and"
            " gets `-1`, because section 7.25 gives it no colour and the field is not nullable. |",
            '| `AgentInfo.display_name` | `"<agent_id> <harness_id>"`. |',
            "| `Decision.headline` | tick, seat, source, block shape and markets touched, so a text"
            " search has something stable to match when a scripted seat supplied no rationale. |",
            "| `LeaderboardRow.ci_low` / `.ci_high` | `mu` plus or minus three sigma, the conventional"
            " TrueSkill display interval. The store keeps `mu` and `sigma` and nothing else per harness. |",
            "| `Elites.axes` / `.bins` | the leading descriptor names matching the coordinate arity, and"
            " the observed extent of each axis. `save_elites` persists cells and no grid header. |",
            "| `TournamentDetail.kpis` | the seven PRD section 15 names, from `load_costs_usd`,"
            " `load_incidents`, `load_rating_series` and the `match` rows. `heldout_gain_mu_milli` is"
            " reported as `0`: its supplier is `pxe.evolve` and no store reader exposes it. |",
            "",
            "Two virtual ticks are reachable and carry less than a real one, because the journal holds",
            "less: tick `0` is `MatchStarted` (every market open at its prior, no book, no account",
            "snapshot) and tick `ticks_total + 1` is finalisation (the last resolutions and their",
            "settlements, no mark to market and no account snapshot).",
            "",
            "## Payload schemas",
            "",
        ]
    )
    lines.extend(_schema_sections(schema))
    return "\n".join(lines) + "\n"


def _route_rows(schema: Mapping[str, Any]) -> list[str]:
    """Render one markdown table row per declared GET route."""
    rows: list[str] = []
    paths = schema.get("paths", {})
    for path in sorted(paths):
        operations = paths[path]
        for method in sorted(operations):
            if method.upper() != "GET":
                continue
            operation = operations[method]
            query = ", ".join(
                f"`{param['name']}`" for param in operation.get("parameters", ()) if param.get("in") == "query"
            )
            rows.append(f"| GET | `{path}` | {query or '-'} | {_response_name(operation)} |")
    return rows


def _response_name(operation: Mapping[str, Any]) -> str:
    """Name the 200 body of one operation, from its schema reference."""
    content = operation.get("responses", {}).get("200", {}).get("content", {})
    for media in ("application/json", "text/html"):
        block = content.get(media)
        if block is None:
            continue
        schema = block.get("schema", {})
        ref = schema.get("$ref")
        if ref:
            return f"`{_pretty_name(str(ref).rsplit('/', 1)[-1])}`"
        return f"`{media}`"
    return "-"


def _pretty_name(name: str) -> str:
    """Turn FastAPI's generic schema name into the section 7.21 spelling.

    FastAPI names a parametrised model ``Page_MatchSummary_``; section 7.21 and
    ``web/src/api/types.ts`` both spell it ``Page<MatchSummary>``, and the
    generated document is read next to that table.
    """
    if not name.startswith("Page_") or not name.endswith("_"):
        return name
    inner = name[len("Page_") : -1].strip("_")
    if inner.startswith("dict_str"):
        inner = "JournalEvent"
    return f"Page<{inner}>"


def _schema_sections(schema: Mapping[str, Any]) -> list[str]:
    """Render the field table of every payload model, in declaration order."""
    components = schema.get("components", {}).get("schemas", {})
    lines: list[str] = []
    for model in iter_payload_models():
        name = model.__name__
        block = components.get(name)
        if block is None:
            continue
        lines.append(f"### `{name}`")
        lines.append("")
        doc = (model.__doc__ or "").strip().splitlines()
        if doc:
            lines.append(_prose(doc[0]))
            lines.append("")
        lines.append("| Field | Type | Required |")
        lines.append("|---|---|---|")
        required = frozenset(block.get("required", ()))
        for field_name, field_schema in block.get("properties", {}).items():
            lines.append(
                f"| `{field_name}` | `{_cell(_type_of(field_schema))}` | {'yes' if field_name in required else 'no'} |"
            )
        lines.append("")
    lines.extend(_generic_sections(components))
    return lines


def _generic_sections(components: Mapping[str, Any]) -> list[str]:
    """Render the ``Page<T>`` instantiations FastAPI names with a suffix."""
    lines: list[str] = []
    for name in sorted(components):
        if not name.startswith("Page"):
            continue
        block = components[name]
        lines.append(f"### `{name}`")
        lines.append("")
        lines.append("One page of a listing. `total` counts the whole collection.")
        lines.append("")
        lines.append("| Field | Type | Required |")
        lines.append("|---|---|---|")
        required = frozenset(block.get("required", ()))
        for field_name, field_schema in block.get("properties", {}).items():
            lines.append(
                f"| `{field_name}` | `{_cell(_type_of(field_schema))}` | {'yes' if field_name in required else 'no'} |"
            )
        lines.append("")
    return lines


def _prose(text: str) -> str:
    """Turn a reStructuredText docstring line into plain markdown.

    The models are documented for a Python reader, and the generated file is
    read by a TypeScript one: the double backtick literals and the Sphinx roles
    would be noise in the table it sits above.

    Args:
        text: One docstring line.

    Returns:
        The markdown form.
    """
    cleaned = re.sub(_ROLE_PATTERN, _ROLE_REPLACEMENT, text)
    return cleaned.replace("``", "`")


def _cell(text: str) -> str:
    """Escape a value so it survives inside a markdown table cell.

    A union type renders as ``string | null`` and the pipe would end the cell,
    silently shifting every following column of the row.

    Args:
        text: The rendered type.

    Returns:
        The escaped form.
    """
    return text.replace("|", r"\|")


def _type_of(field_schema: Mapping[str, Any]) -> str:
    """Render one JSON Schema fragment as a short type name."""
    ref = field_schema.get("$ref")
    if ref:
        return str(ref).rsplit("/", 1)[-1]
    if "anyOf" in field_schema:
        return " | ".join(_type_of(option) for option in field_schema["anyOf"])
    if "items" in field_schema:
        return f"{_type_of(field_schema['items'])}[]"
    if "const" in field_schema:
        return json.dumps(field_schema["const"])
    if "enum" in field_schema:
        return " | ".join(json.dumps(value) for value in field_schema["enum"])
    kind = field_schema.get("type")
    if kind is None:
        return "unknown"
    return str(kind)


def write_sample_fixtures(
    app: FastAPI, *, match_id: str, out_dir: Path, tournament_id: str | None = None
) -> tuple[Path, ...]:
    """Write one JSON fixture per payload into ``web/tests/fixtures/``.

    This is the ``--samples`` half of ``pxe api openapi`` (section 7.22). The
    samples are produced by the real route builders against a real recorded
    match, which is what section 7.25 requires: A24 builds its whole
    application on these files, and a hand written fixture would let it build
    against a fiction.

    Args:
        app: The application, normally :func:`create_app`.
        match_id: The recorded match to sample.
        out_dir: Destination directory, normally ``web/tests/fixtures``.
        tournament_id: A recorded tournament to sample as well, or ``None``.

    Returns:
        The written paths, sorted.
    """
    service: ReplayService = app.state.replay_service
    payloads = sample_payloads(service, match_id=match_id, tournament_id=tournament_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in sorted(payloads):
        path = out_dir / f"{name}.json"
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payloads[name], indent=2, sort_keys=False, ensure_ascii=False) + "\n")
        written.append(path)
    return tuple(written)


def payload_models() -> Iterable[type[BaseModel]]:
    """Yield every payload model, for a caller that wants to validate a fixture."""
    return iter_payload_models()
