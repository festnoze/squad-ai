# Docker Delivery — build, deploy & network-verify every project (fix-until-green)

**Goal.** Autospec today ends a project's lifecycle at the delivery gates (green
suite → smoke run → runtime acceptance → Definition of Done → `done`) and the
generated app only ever runs as a local host process. `orchestrator/deploy.py`
writes a Dockerfile but **never builds or runs an image**. This upgrade adds a
final automatic pipeline step so each project is (1) **built into a Docker
image**, (2) **deployed** to local Docker Desktop on a **common network
`autospec-net`** shared by all Autospec projects, (3) **verified** — container
boots healthy AND every deployed Autospec container reaches every other one over
the network (container-name DNS, HTTP probes) — and (4) **repaired** in a
fix-until-green loop reusing `_arepair_delivery`, with infra conditions (daemon
down…) parking in `needs_attention` **without burning repair attempts**.

**Thesis.** Same discipline as the verified-swarm upgrade: every task ships with
an *executed* check. A green pytest suite proves the code compiles and tests
pass — it does **not** prove the app boots in a container, binds `0.0.0.0`,
ships its `frontend/dist`, or is reachable by its siblings. The Docker delivery
gate makes that runnability an executed truth, and a failed one is a *repairable*
signal fed back to a Dev agent — never a self-report.

---

## ✅ Confirmed decisions (user)

These decisions are frozen and drive every task below:

| Decision | Choice |
|---|---|
| Communication check | **Health + cross-container reachability only** (no app-level API coupling). |
| Network topology | **One shared external network `autospec-net`** for all Autospec projects (container-name DNS). |
| Scope | Web-facing projects: python web backends (`api`/`web-ssr`/`fullstack` or auto-detected) **plus frontend-only SPAs** (nginx static image). |
| CLI / library projects | **Skip with an explicit warning** (`deploy_status="skipped"`), never auto-containerized. |
| Repair loop | **Reuse `_arepair_delivery`** with its `INTEGRATION_FIX_ATTEMPTS` budget (no new `DOCKER_FIX_ATTEMPTS`). |
| Fullstack packaging | **ONE image** (multi-stage: frontend built and served by the backend), matching the runtime-acceptance INTEGRATED model. |
| Frontend-only packaging | **`nginx:alpine` static image** (multi-stage build → nginx serve, container port 80, SPA `try_files` fallback). |
| Infra vs repairable | Infra (daemon absent, network un-creatable) **parks in `needs_attention` without burning attempts**; only failures attributable to the current project are repairable. |
| Cross-project attribution | Only pairs **involving the current project** fail its gate; foreign pairs are warnings. |

---

## Design principles (invariants)

1. **Executed runnability is non-negotiable.** The container must actually boot
   and answer HTTP; reachability is proved by real `docker exec` probes between
   containers, not by any agent's narrative.
2. **Infra is parked, not repaired.** A missing daemon or un-creatable network is
   an environment condition — it parks the delivery in `needs_attention` and
   burns **zero** repair attempts (mirrors the runtime-acceptance exit-code `2`
   contract).
3. **Attribution is strict.** A failing reachability pair only fails the gate when
   the **current** project is one of its endpoints; failures between two foreign
   projects are surfaced as warnings and never consume the current project's
   attempts.
4. **Reuse-first.** The repair loop is the existing `_arepair_delivery` (git
   snapshot, Dev agent, pytest guard + rollback, re-run gate); Docker only threads
   a `prompt_builder` and a Docker-specific `averify`.
5. **Flag-gated, default OFF.** `DOCKER_DELIVERY=0` ⇒ byte-identical legacy
   behavior. Enabling requires Docker Desktop; it is **not** in the `verified`
   preset (profile/env-driven only).
6. **Autospec owns its Dockerfile, never the user's.** A `# autospec:managed`
   marker on line 1 lets Autospec regenerate its own Dockerfile but never clobber
   a hand-edited one.

---

## Wave 1 — Settings, state & Dockerfile template

**Outcome:** the configuration surface, persisted deploy state, and the
image-build templates the daemon layer will consume — all additive, all
default-off.

### T1.1 — Settings (`backend/autospec/config.py`)
Near the sandbox/docker block, same `_env_*` patterns:
`docker_delivery` (`DOCKER_DELIVERY`, default `False`), `docker_network`
(`DOCKER_NETWORK`, default `autospec-net`), `docker_build_timeout_s`
(`DOCKER_BUILD_TIMEOUT_S`, `600.0`, min `30.0`), `docker_deploy_timeout_s`
(`DOCKER_DEPLOY_TIMEOUT_S`, `60.0`, min `5.0`, health wait),
`docker_host_port_base` (`DOCKER_HOST_PORT_BASE`, `18000`, min `1024`). Reuse the
existing `docker_cmd` (`DOCKER_CMD`) and `integration_fix_attempts`. Document in
`backend/.env.example`.

### T1.2 — State (`models.py` + `orchestrator/delivery_state.py`)
`ProjectState` after `delivery_partial`: `deploy_status`
(`"" | building | deploying | verifying | deployed | failed | skipped`),
`deployed_image`, `deployed_container`, `deploy_host_port` (stable, reused across
redeploys), `deploy_detail` (~2000 chars). Defaults keep old persisted states
loadable. `delivery_state.set_deploy(...)` is the single mutation point;
`reset(...)` clears `deploy_status`/`deploy_detail` but keeps `deploy_host_port`
and names (old container keeps running while the next iteration builds).

### T1.3 — Dockerfile template (`orchestrator/deploy.py`)
Replace `_DOCKERFILE` with `dockerfile_text(port, kind)`, `kind ∈ {backend,
fullstack, frontend}`, first line `# autospec:managed`:
- **backend** — current content + `EXPOSE {port}`.
- **fullstack** — multi-stage `node:20-alpine AS fe` (`npm ci || npm install`,
  `npm run build`) → python stage, `COPY --from=fe /fe/dist ./frontend/dist`,
  `EXPOSE {port}` — ONE image, backend serves the SPA.
- **frontend** — `node:20-alpine AS fe` build → `nginx:alpine`,
  `COPY --from=fe /fe/dist /usr/share/nginx/html`, `EXPOSE 80`, minimal
  `try_files` SPA-fallback nginx conf written alongside.
`.dockerignore` adds `node_modules`/`**/node_modules`. New signature
`write_deploy_artifacts(ws, *, port=None, kind="backend")`: Dockerfile (re)written
when absent OR managed-marked and content differs; `.dockerignore`/`ci.yml` keep
never-overwrite semantics.

**Effort:** S. **Risk:** low — additive settings, backward-compatible state
defaults, managed-marker guards user Dockerfiles.

---

## Wave 2 — Daemon layer & deploy/verify entry point

**Outcome:** `orchestrator/docker_deploy.py`, the single module that talks to the
daemon and exposes one entry point (`deploy_and_verify`) used both by the pipeline
phase and as the repair `averify`.

### T2.1 — Module skeleton (`orchestrator/docker_deploy.py`)
`DockerDeployResult(ok, detail, skipped=False, infra=False, image="",
container="", host_port=0)`; labels `LABEL_PROJECT="autospec.project"`,
`LABEL_PORT="autospec.port"`. `slug/image_name/container_name(project_id)` →
`autospec/<slug>:latest`, `autospec-<slug>` (sanitize `[^a-z0-9-]`). All
subprocess sync (mirrors `runtime_acceptance`), called via `asyncio.to_thread`.

### T2.2 — Daemon primitives
`_docker(args, *, timeout, cwd=None)` (OSError/Timeout → `(-1, str(exc))`);
`docker_available()` (`docker version --format {{.Server.Version}}`);
`looks_like_daemon_down(output)` (named-pipe / "cannot connect to the docker
daemon" / "error during connect" / command-not-found → **infra**);
`ensure_network(network)` (inspect, create if missing, tolerate "already exists");
`build_image(ws, image, *, timeout, on_line=None)` (`Popen` streaming, returns
`(rc==0, tail)`); `replace_container(...)` (`rm -f` old, then `run -d` with
`--network`, `-p host:container`, `--label autospec.project/port`,
`--restart unless-stopped`).

### T2.3 — Health & reachability
`wait_healthy(name, host_port, *, timeout)` polls 1 s: `docker inspect` state
(`exited`/`dead` → fail fast with `docker logs`), HTTP GET on the host port —
**any status (incl. 404) = healthy**; timeout → logs (repairable). `list_deployed()`
via `docker ps --filter label`. `probe(src, dst, dst_port)` (`docker exec` python
`urllib`, fallback busybox `wget`; `HTTPError` = reachable).
`check_cross_reachability(own_container, deployed)` — full matrix; own-pair fail ⇒
gate failure, foreign-pair fail ⇒ warning.

### T2.4 — Lifecycle & entry point
`undeploy(project_id)` (`rm -f` + best-effort `rmi`); `allocate_host_port(state)`
(reuse persisted; else scan from `docker_host_port_base` skipping label-claimed,
persisted-state and host-busy ports); `should_run(state, ws, *, enabled)` returns
the deploy `kind` (fullstack/backend/frontend) or a skip reason.
`deploy_and_verify(...)` — the **single entry point**: docker_available→infra;
ensure_network→infra; build→repairable; replace_container→repairable;
wait_healthy→repairable; cross-reachability→repairable for own pairs.

**Effort:** M. **Risk:** medium — daemon interaction; all subprocess-faked in
tests.

---

## Wave 3 — Repair prompt, pipeline phase & profiles

**Outcome:** the Docker gate wired into `_alifecycle` between DoD and document,
with a dedicated repair prompt and profile overrides.

### T3.1 — Repair prompt + hook (`agents/prompts.py`, `pipeline.py`)
New `dev_fix_deploy(package_name, report, architecture="", attempt=1,
max_attempts=1)` modeled on `dev_fix_integration`. Classic causes: app binds
`127.0.0.1` not `0.0.0.0`; `main.py` port ≠ EXPOSE/label; `frontend/dist` missing
from image; dep in `.venv` but absent from `pyproject.toml` (crashes under
`uv sync --no-dev`); host-layout path assumptions. `_arepair_delivery` gains a
keyword-only `prompt_builder=None` (call site becomes `(prompt_builder or
prompts.dev_fix_integration)(...)`; existing callers untouched). Extend
`_smoke_looks_like_infra` with daemon-down patterns so an infra-shaped report can
never enter the repair loop.

### T3.2 — Pipeline phase (`pipeline.py`)
`_adocker_delivery_phase(self) -> bool` slotted between `_apply_definition_of_done`
and `_adocument_phase`. Mirrors `_asmoke_phase`/`_aruntime_acceptance_phase`:
`should_run` skip-with-warning; `monitor.phase("docker")`; regenerate artifacts;
infra pre-check → `_apark_infra`; `allocate_host_port` → persist; `set_deploy`
transitions building→deploying→verifying; `deploy_and_verify` via
`asyncio.to_thread` streaming build lines; `result.infra` → park; repairable →
`_arepair_delivery(..., prompt_builder=prompts.dev_fix_deploy)`; success →
`deployed` + chat 🐳; failure → `failed` + `_block_delivery`. Rework
`Pipeline.adeploy()` (background `_deploy_task`, gate flag bypassed but
FAKE_AGENTS/web-candidate skips kept) and add `Pipeline.aundeploy()`.

### T3.3 — Profiles (`orchestrator/profiles.py`)
Add `"docker_delivery"` to overrides: **True** for `api`, `web-ssr`, `fullstack`;
**False** for `library-fast`, `cli`, `brownfield` (never auto-containerize an
existing repo). `auto` stays override-free → env decides.

**Effort:** M. **Risk:** medium — touches the lifecycle hot path; guarded by the
default-off flag and the byte-identical-when-off regression tests.

---

## Wave 4 — API, frontend & tests

**Outcome:** the HTTP surface, the RunPanel deploy chip, and the full test
footprint (module + phase layers, no real docker).

### T4.1 — API (`api/server.py`)
`POST /api/projects/{id}/deploy` (same route) → `{"created": [...],
"deploy_started": bool}`; new `POST /api/projects/{id}/undeploy` →
`pipeline.aundeploy()` (404/409/200). Project delete endpoint: best-effort
`docker_deploy.undeploy(project_id)` before wiping the workspace (no zombie
containers). No new streaming plumbing: deploy fields ride `_sync()` → EventBus →
SSE/WS; build lines ride `self._log("docker", …)`.

### T4.2 — Frontend (`frontend/src`)
`types.ts` deploy fields; `api.ts` `deployProject` return type + new
`undeployProject`. `RunPanel.tsx` deploy chip (🐳 green link when `deployed`, red
with `title=deploy_detail` when `failed`, pulsing while building/deploying/
verifying, « Undeploy » action). i18n `{en, fr}` keys in `runPanel.ts`/`app.ts`.

### T4.3 — Tests (`backend/tests/test_docker_delivery.py` + touched suites)
Module layer (fake `subprocess.run`/`Popen`): daemon-down → infra; `ensure_network`
idempotent; `wait_healthy` exited/404/timeout; `check_cross_reachability`
own-vs-foreign; `allocate_host_port` reuse/collision/base; name sanitization.
Phase layer (reuse `repair_env` + `FakeRunner` + queued `deploy_and_verify`): gate
off / fake_agents / CLI → skipped, zero docker calls; daemon down → park, zero
agent calls; build failure → repair → green (`dev_fix_deploy` wording); exhausted
attempts → blocked; repair breaking pytest → rollback. Touched: `test_deploy.py`
(three dockerfile variants, managed-marker), `test_profiles.py` (override per
profile), `test_api.py` (deploy response, undeploy 404/409/200),
`test_integration_repair.py` (`prompt_builder` routing).

**Effort:** M. **Risk:** low — all docker calls monkeypatched; no real daemon in
CI.

---

## Key edge cases

- **Windows Docker Desktop off** → `docker version` named-pipe connect error →
  infra → park, zero attempts (matches exit-2 contract).
- **Port collisions** → label scan + persisted-state scan + host bind-test +
  stable persisted `deploy_host_port`; container-internal port always
  `resolve_web_port(ws)` so gate, `EXPOSE` and probes agree.
- **Stale containers of deleted projects** → best-effort undeploy on delete;
  label-based `list_deployed` means orphans drop out of the matrix when they die.
- **FAKE_AGENTS demo mode** → skipped in `should_run`; no real docker in demo or
  unit tests.
- **Cross-project attribution** → only pairs involving the current project fail
  its gate; foreign failures are warnings.
- **Probe tooling per image** → python images have no curl/wget, nginx:alpine has
  no python: probe tries `python -c urllib` then falls back to busybox `wget`;
  `HTTPError` = reachable.
- **Frontend-only dist path (Angular vs Vite)** → Autospec scaffolds Vite
  (`dist/`); an Angular-style output path breaks the `COPY --from=fe /fe/dist`
  step → repairable build failure the `dev_fix_deploy` agent fixes.
- **127.0.0.1 binding in-container** → fails health+reachability → repairable,
  first cause in `dev_fix_deploy`.

---

## Config additions (default OFF ⇒ byte-identical legacy behavior)

| Env var | Setting | Wave | Purpose |
|---|---|---|---|
| `DOCKER_DELIVERY` | `docker_delivery` | 1 | Enable the build + deploy + network-verify gate. |
| `DOCKER_NETWORK` | `docker_network` | 1 | Shared external network for all Autospec containers (default `autospec-net`). |
| `DOCKER_BUILD_TIMEOUT_S` | `docker_build_timeout_s` | 1 | `docker build` timeout (default `600`, min `30`). |
| `DOCKER_DEPLOY_TIMEOUT_S` | `docker_deploy_timeout_s` | 1 | Health-wait after container start (default `60`, min `5`). |
| `DOCKER_HOST_PORT_BASE` | `docker_host_port_base` | 1 | Host-port scan base (default `18000`, min `1024`). |
| `DOCKER_CMD` | `docker_cmd` | — | Docker binary (pre-existing, reused). |
| *(reused)* | `integration_fix_attempts` | 3 | Repair-loop budget (shared with the integration gate; no new flag). |

---

## Verification

```
cd backend
uv run pytest tests/test_docker_delivery.py tests/test_deploy.py tests/test_profiles.py tests/test_api.py tests/test_integration_repair.py -q
uv run pytest -q                 # full suite; no real docker (all monkeypatched)

cd ../frontend
npm run test -- --run            # Vitest incl. RunPanel deploy-chip cases
npm run build                    # tsc + vite build stays green
```

Manual E2E (real Docker Desktop): `DOCKER_DELIVERY=1`, run a `fullstack` project
end-to-end; then `docker ps --filter label=autospec.project`,
`docker network inspect autospec-net`, browse `http://localhost:<deploy_host_port>`;
create a second project and confirm the cross-reachability matrix in the docker
logs/chat.

---

## Shipped-status table

| Wave | Shipped | Key modules / hooks |
|---|---|---|
| 1 — settings, state, Dockerfile template | ☐ | `config.py` (`docker_*`), `models.py` + `delivery_state.set_deploy`, `deploy.dockerfile_text` (`# autospec:managed`) |
| 2 — daemon layer & entry point | ☐ | `orchestrator/docker_deploy.py` (`docker_available`, `ensure_network`, `build_image`, `replace_container`, `wait_healthy`, `check_cross_reachability`, `deploy_and_verify`) |
| 3 — repair prompt, phase & profiles | ☐ | `prompts.dev_fix_deploy`, `_arepair_delivery(prompt_builder=…)`, `_adocker_delivery_phase`, `Pipeline.adeploy/aundeploy`, `profiles.py` overrides |
| 4 — API, frontend & tests | ☐ | `POST /deploy` + `/undeploy`, delete-endpoint undeploy, `RunPanel` deploy chip, `test_docker_delivery.py` + touched suites |
