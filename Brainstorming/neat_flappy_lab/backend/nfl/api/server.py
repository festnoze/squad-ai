"""FastAPI app: config schema endpoints + a WebSocket that drives the engine.

Design
------
Each WebSocket connection owns one :class:`Session`. All engine work runs in a
single background **worker thread**; the async side never touches the runner
directly. Communication is one-way and race-free:

* Client messages are validated on the async side and pushed as *commands* onto a
  thread-safe queue (``config`` / ``control`` / ``select``).
* The worker drains commands at generation boundaries, runs generations when
  playing, and emits messages back to the socket via ``run_coroutine_threadsafe``.

Outgoing messages: ``frame`` (per tick, watch mode), ``generation`` (per gen),
``genome`` (reply to select), ``config`` (current config echo), ``error``.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ..config import SimConfig, StreamMode
from ..engine.runner import Runner
from ..engine.snapshots import frame_message, generation_message, genome_message
from ..lessons.demos import linear_regression_demo, neat_intro_demo, quadratic_network_demo
from .schema import config_defaults_dict, config_schema_dict, is_structural_change

app = FastAPI(title="neat_flappy_lab")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/config/schema")
def config_schema() -> dict:
    """JSON schema used by the frontend to auto-generate its controls."""
    return config_schema_dict()


@app.get("/config/defaults")
def config_defaults() -> dict:
    """Default config values."""
    return config_defaults_dict()


@app.get("/lessons/linear")
def lesson_linear(steps: int = 80, lr: float = 0.08, seed: int = 4) -> dict:
    """Trace a tiny linear regression optimized by gradient descent."""
    return linear_regression_demo(steps=steps, lr=lr, seed=seed)


@app.get("/lessons/quadratic")
def lesson_quadratic(
    steps: int = 160,
    lr: float = 0.035,
    hidden: int = 6,
    seed: int = 7,
) -> dict:
    """Trace a small neural network fitting a quadratic function."""
    return quadratic_network_demo(steps=steps, lr=lr, hidden=hidden, seed=seed)


@app.get("/lessons/neat-intro")
def lesson_neat_intro(generations: int = 32, seed: int = 11) -> dict:
    """Return a compact NEAT-style XOR evolution trace."""
    return neat_intro_demo(generations=generations, seed=seed)


class Session:
    """One connection's engine, driven by a background worker thread."""

    def __init__(self, ws: WebSocket, loop: asyncio.AbstractEventLoop) -> None:
        self.ws = ws
        self.loop = loop
        self.config = SimConfig()
        self.runner = Runner(self.config)

        self._commands: queue.Queue[dict] = queue.Queue()
        self._stop = threading.Event()
        self._playing = False
        self._step_pending = False
        # Selection is handled out-of-band (atomic int write) so it applies LIVE,
        # mid-episode, instead of waiting for the next generation boundary.
        self._pending_select: int | None = None
        self._worker = threading.Thread(target=self._run, daemon=True)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self._worker.start()

    def shutdown(self) -> None:
        self._stop.set()

    def submit(self, command: dict) -> None:
        """Enqueue a validated command for the worker (called from async side)."""
        self._commands.put(command)

    def request_select(self, bird_id: int) -> None:
        """Request a live selection change (consumed on the next tick/loop)."""
        self._pending_select = int(bird_id)

    def _consume_select(self) -> None:
        """Apply a pending selection: set it on the runner and reply with its genome."""
        sel = self._pending_select
        if sel is None:
            return
        self._pending_select = None
        self.runner.select_bird(sel)
        genomes = self.runner.population.genomes
        if 0 <= sel < len(genomes):
            self._emit(genome_message(sel, genomes[sel].to_dict()))

    # --------------------------------------------------------------------- output
    def _emit(self, message: dict) -> None:
        """Send a message to the socket from the worker thread.

        Robust to a closed/closing event loop: scheduling onto a closed loop
        raises synchronously, so the whole thing is guarded and simply stops the
        worker if the socket is gone.
        """
        if self._stop.is_set():
            return
        try:
            fut = asyncio.run_coroutine_threadsafe(self.ws.send_json(message), self.loop)
            fut.result(timeout=5.0)
        except Exception:
            # Socket/loop likely gone; stop the worker quietly.
            self._stop.set()

    def _on_frame(self, render_state: dict, activations: dict) -> None:
        # Apply any pending selection live, every tick, even mid-episode.
        self._consume_select()
        if self.config.stream_mode != StreamMode.watch:
            return
        self._emit(frame_message(render_state, activations, self.runner.population.generation))
        # Pace playback to roughly 60*sim_speed ticks per second.
        time.sleep(max(0.0, 1.0 / (60.0 * max(self.config.sim_speed, 0.01))))

    # --------------------------------------------------------------------- worker
    def _drain_commands(self) -> None:
        while True:
            try:
                cmd = self._commands.get_nowait()
            except queue.Empty:
                return
            self._apply_command(cmd)

    def _apply_command(self, cmd: dict) -> None:
        kind = cmd.get("cmd")
        if kind == "config":
            new_config: SimConfig = cmd["config"]
            structural = is_structural_change(self.config, new_config)
            self.config = new_config
            self._emit({"type": "config", "config": new_config.model_dump(mode="json")})
            if structural:
                # A structural change starts a fresh run: rebuild and clear the UI.
                self.runner = Runner(new_config)
                self._playing = False
                self._emit({"type": "reset", "ok": True})
            else:
                # Soft params apply live (mutation rates, lr, mode, speed, ...).
                self.runner.config = new_config
                self.runner.population.config = new_config
                self.runner.env.config = new_config
        elif kind == "control":
            action = cmd.get("action")
            if action == "play":
                self._playing = True
            elif action == "pause":
                self._playing = False
            elif action == "step":
                self._step_pending = True
            elif action == "reset":
                self.runner = Runner(self.config)
                self._playing = False
                self._emit({"type": "reset", "ok": True})

    def _run(self) -> None:
        # Greet with current config so the UI can populate immediately.
        self._emit({"type": "config", "config": self.config.model_dump(mode="json")})
        while not self._stop.is_set():
            self._drain_commands()
            self._consume_select()
            if self._stop.is_set():
                break
            if self._playing or self._step_pending:
                on_frame = self._on_frame if self.config.stream_mode == StreamMode.watch else None
                try:
                    stats = self.runner.step_generation(on_frame=on_frame)
                except Exception as exc:  # keep the socket alive, report the failure
                    self._emit({"type": "error", "message": f"generation failed: {exc!r}"})
                    self._playing = False
                    continue
                self._emit(generation_message(stats))
                if self._step_pending:
                    self._step_pending = False
                    self._playing = False
            else:
                time.sleep(0.03)


def _parse_config(session: Session, patch: dict) -> SimConfig:
    """Merge a partial patch onto the session config and validate it."""
    merged = session.config.model_dump()
    merged.update(patch or {})
    return SimConfig(**merged)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    loop = asyncio.get_running_loop()
    session = Session(ws, loop)
    session.start()
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "config":
                try:
                    new_config = _parse_config(session, msg.get("patch", {}))
                except Exception as exc:
                    await ws.send_json({"type": "error", "message": f"invalid config: {exc}"})
                    continue
                session.submit({"cmd": "config", "config": new_config})
            elif kind == "control":
                session.submit({"cmd": "control", "action": msg.get("action")})
            elif kind == "select":
                session.request_select(int(msg.get("birdId", 0)))
            else:
                await ws.send_json({"type": "error", "message": f"unknown message type: {kind}"})
    except WebSocketDisconnect:
        session.shutdown()
    except Exception:
        session.shutdown()
        raise
