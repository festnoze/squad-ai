"""The sqlite run index (CONTRACTS_V2 sections 12.6, 12.8 and 12.12).

Three consumers need to ask questions across runs that no single ``runs/<run_id>/`` directory can
answer: ``GET /runs`` lists them (section 12.12), ``pmx claim`` counts the distinct genome hashes ever
scored against a dataset to compute the ``K`` of its deflation (section 12.6, ruling R72), and the claim
ledger needs a monotone ``created_at_index`` that is not a clock (section 12.8). This module is that
index and nothing more: it is a **cache over the artefacts**, every row is rebuildable from
``runs/<run_id>/manifest.json`` and ``journal.jsonl``, and deleting the file loses no evidence.

Two rules it keeps rather than documents:

* **No wall clock and no uuid.** ``created_at_index`` is a counter over the rows already indexed, so
  the same sequence of runs indexed on two machines produces the same index. A timestamp column would
  put a clock inside a number the claim ledger chains.
* **Idempotence.** Indexing a run twice keeps its first ``created_at_index`` and overwrites the rest, so
  a re-indexed directory does not inflate ``K`` and does not reorder the ledger.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from pmx.errors import InvalidConfigError
from pmx.metrics.projection import RunHandle

__all__ = ("CandidateRow", "DEFAULT_STORE_NAME", "RunRow", "RunStore")

#: The index lives beside the run directories it indexes.
DEFAULT_STORE_NAME = "index.sqlite"

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id           TEXT PRIMARY KEY,
        kind             TEXT NOT NULL,
        dataset_name     TEXT NOT NULL,
        dataset_hash     TEXT NOT NULL,
        market_ids_hash  TEXT NOT NULL,
        fold             TEXT NOT NULL,
        seed             INTEGER NOT NULL,
        config_hash      TEXT NOT NULL,
        n_bars           INTEGER NOT NULL,
        n_events         INTEGER NOT NULL,
        journal_hash     TEXT NOT NULL,
        created_at_index INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidates (
        dataset_hash    TEXT NOT NULL,
        genome_hash     TEXT NOT NULL,
        agent_id        TEXT NOT NULL,
        run_id          TEXT NOT NULL,
        fold            TEXT NOT NULL,
        skill_lb_micro  INTEGER NOT NULL,
        pnl_lb_cents    INTEGER NOT NULL,
        PRIMARY KEY (dataset_hash, genome_hash, run_id, agent_id, fold)
    )
    """,
    "CREATE INDEX IF NOT EXISTS runs_by_dataset ON runs (dataset_hash, created_at_index)",
    "CREATE INDEX IF NOT EXISTS candidates_by_dataset ON candidates (dataset_hash, genome_hash)",
)


@dataclass(frozen=True, slots=True)
class RunRow:
    """One indexed run: exactly the fields ``GET /runs`` answers with (section 12.12)."""

    run_id: str
    kind: str
    dataset_name: str
    dataset_hash: str
    market_ids_hash: str
    fold: str
    seed: int
    config_hash: str
    n_bars: int
    n_events: int
    journal_hash: str
    created_at_index: int

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "dataset_name": self.dataset_name,
            "dataset_hash": self.dataset_hash,
            "market_ids_hash": self.market_ids_hash,
            "fold": self.fold,
            "seed": self.seed,
            "config_hash": self.config_hash,
            "n_bars": self.n_bars,
            "n_events": self.n_events,
            "journal_hash": self.journal_hash,
            "created_at_index": self.created_at_index,
        }


@dataclass(frozen=True, slots=True)
class CandidateRow:
    """One genome scored against one dataset on one fold: the raw material of ``candidates_store``."""

    dataset_hash: str
    genome_hash: str
    agent_id: str
    run_id: str
    fold: str
    skill_lb_micro: int
    pnl_lb_cents: int

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_hash": self.dataset_hash,
            "genome_hash": self.genome_hash,
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "fold": self.fold,
            "skill_lb_micro": self.skill_lb_micro,
            "pnl_lb_cents": self.pnl_lb_cents,
        }


def _as_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise InvalidConfigError("the run index holds a non-integer where an integer belongs")


def _as_str(value: object) -> str:
    if isinstance(value, str):
        return value
    raise InvalidConfigError("the run index holds a non-string where a string belongs")


def _run_row(record: Sequence[object]) -> RunRow:
    return RunRow(
        run_id=_as_str(record[0]),
        kind=_as_str(record[1]),
        dataset_name=_as_str(record[2]),
        dataset_hash=_as_str(record[3]),
        market_ids_hash=_as_str(record[4]),
        fold=_as_str(record[5]),
        seed=_as_int(record[6]),
        config_hash=_as_str(record[7]),
        n_bars=_as_int(record[8]),
        n_events=_as_int(record[9]),
        journal_hash=_as_str(record[10]),
        created_at_index=_as_int(record[11]),
    )


_RUN_COLUMNS = (
    "run_id, kind, dataset_name, dataset_hash, market_ids_hash, fold, seed, config_hash, "
    "n_bars, n_events, journal_hash, created_at_index"
)


class RunStore:
    """The run index, opened on one file (or in memory for a test).

    The connection is owned by the instance and closed by :meth:`close` or by leaving the context
    manager. Every write commits immediately: an index that lost the last run of an interrupted
    evolution would understate ``K`` and make a claim easier than it should be.
    """

    __slots__ = ("_connection", "_path")

    def __init__(self, path: Path | str) -> None:
        """Open (and create when missing) the index at ``path``, or in memory for ``":memory:"``."""
        self._path = Path(path)
        if str(path) == ":memory:":
            self._connection = sqlite3.connect(":memory:")
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(str(self._path))
        with closing(self._connection.cursor()) as cursor:
            for statement in _SCHEMA:
                cursor.execute(statement)
        self._connection.commit()

    @classmethod
    def in_memory(cls) -> RunStore:
        """A store that lives for the length of the process: the shape every unit test wants."""
        return cls(":memory:")

    @property
    def path(self) -> Path:
        """The file the index lives in (``:memory:`` for an in-memory store)."""
        return self._path

    def close(self) -> None:
        """Commit and close. Idempotent."""
        self._connection.commit()
        self._connection.close()

    def __enter__(self) -> RunStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # ----------------------------------------------------------------------
    # Writing
    # ----------------------------------------------------------------------
    def next_created_at_index(self) -> int:
        """The index the next indexed run (or claim) takes: one past the largest one indexed.

        Not a clock and not a uuid: the ledger of section 12.8 chains on it, and a chain whose order
        depended on a machine's clock would be unverifiable on another machine.
        """
        with closing(self._connection.cursor()) as cursor:
            cursor.execute("SELECT COALESCE(MAX(created_at_index), 0) FROM runs")
            return _as_int(cursor.fetchone()[0]) + 1

    def index_run(
        self,
        handle: RunHandle,
        *,
        dataset_name: str,
        seed: int,
        fold: str,
        market_ids_hash: str,
        kind: str = "backtest",
    ) -> RunRow:
        """Index one finished run, or refresh the row of a run already indexed.

        ``dataset_name``, ``seed``, ``fold`` and ``market_ids_hash`` are arguments because a
        :class:`~pmx.metrics.projection.RunHandle` carries the hashes and the projection but not the
        dataset's name or the config's own fields; the caller (``pmx.cli_run``, O2's ``run_generation``,
        O4's ``claim``) holds the ``RunConfig`` that has them.
        """
        existing = self.run(handle.run_id)
        created_at_index = (
            existing.created_at_index if existing is not None else self.next_created_at_index()
        )
        row = RunRow(
            run_id=handle.run_id,
            kind=kind,
            dataset_name=dataset_name,
            dataset_hash=handle.dataset_hash,
            market_ids_hash=market_ids_hash,
            fold=fold,
            seed=seed,
            config_hash=handle.config_hash,
            n_bars=handle.n_bars,
            n_events=handle.n_events,
            journal_hash=handle.journal_hash,
            created_at_index=created_at_index,
        )
        with closing(self._connection.cursor()) as cursor:
            cursor.execute(
                f"INSERT OR REPLACE INTO runs ({_RUN_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.run_id,
                    row.kind,
                    row.dataset_name,
                    row.dataset_hash,
                    row.market_ids_hash,
                    row.fold,
                    row.seed,
                    row.config_hash,
                    row.n_bars,
                    row.n_events,
                    row.journal_hash,
                    row.created_at_index,
                ),
            )
        self._connection.commit()
        return row

    def index_candidate(self, candidate: CandidateRow) -> None:
        """Record that one genome was scored against one dataset on one fold (section 12.6's ``K``)."""
        with closing(self._connection.cursor()) as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO candidates "
                "(dataset_hash, genome_hash, agent_id, run_id, fold, skill_lb_micro, pnl_lb_cents) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    candidate.dataset_hash,
                    candidate.genome_hash,
                    candidate.agent_id,
                    candidate.run_id,
                    candidate.fold,
                    candidate.skill_lb_micro,
                    candidate.pnl_lb_cents,
                ),
            )
        self._connection.commit()

    def index_projection(self, handle: RunHandle, *, fold: str) -> int:
        """Record every agent of a finished run as a candidate against its dataset.

        Returns the number of rows written. This is the call that makes ``candidates_store`` count what
        section 12.6 says it counts ("distinct genome hashes ever scored against this dataset_hash"):
        every agent of every run, not only the ones an evolution reported.
        """
        written = 0
        for result in handle.projection.agents:
            if not result.genome_hash:
                continue
            self.index_candidate(
                CandidateRow(
                    dataset_hash=handle.dataset_hash,
                    genome_hash=result.genome_hash,
                    agent_id=result.agent_id,
                    run_id=handle.run_id,
                    fold=fold,
                    skill_lb_micro=result.skill.lower,
                    pnl_lb_cents=result.pnl.lower,
                )
            )
            written += 1
        return written

    # ----------------------------------------------------------------------
    # Reading
    # ----------------------------------------------------------------------
    def run(self, run_id: str) -> RunRow | None:
        """One indexed run, or ``None``."""
        with closing(self._connection.cursor()) as cursor:
            cursor.execute(f"SELECT {_RUN_COLUMNS} FROM runs WHERE run_id = ?", (run_id,))
            record = cursor.fetchone()
        return None if record is None else _run_row(record)

    def runs(
        self, *, dataset_hash: str | None = None, kind: str | None = None, limit: int | None = None
    ) -> tuple[RunRow, ...]:
        """Indexed runs in ``created_at_index`` order, optionally filtered by dataset or kind."""
        clauses: list[str] = []
        parameters: list[object] = []
        if dataset_hash is not None:
            clauses.append("dataset_hash = ?")
            parameters.append(dataset_hash)
        if kind is not None:
            clauses.append("kind = ?")
            parameters.append(kind)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT {_RUN_COLUMNS} FROM runs{where} ORDER BY created_at_index"
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)
        with closing(self._connection.cursor()) as cursor:
            cursor.execute(query, tuple(parameters))
            return tuple(_run_row(record) for record in cursor.fetchall())

    def genome_hashes(self, dataset_hash: str) -> tuple[str, ...]:
        """Every distinct genome hash ever scored against this dataset, sorted by code point."""
        with closing(self._connection.cursor()) as cursor:
            cursor.execute(
                "SELECT DISTINCT genome_hash FROM candidates WHERE dataset_hash = ? "
                "ORDER BY genome_hash",
                (dataset_hash,),
            )
            return tuple(_as_str(record[0]) for record in cursor.fetchall())

    def candidates_store(self, dataset_hash: str) -> int:
        """``candidates_store`` of section 12.6: how many distinct genomes this dataset has ever seen."""
        return len(self.genome_hashes(dataset_hash))

    def candidates(self, dataset_hash: str) -> tuple[CandidateRow, ...]:
        """Every candidate row of one dataset, in ``(genome_hash, run_id, agent_id, fold)`` order."""
        with closing(self._connection.cursor()) as cursor:
            cursor.execute(
                "SELECT dataset_hash, genome_hash, agent_id, run_id, fold, skill_lb_micro, "
                "pnl_lb_cents FROM candidates WHERE dataset_hash = ? "
                "ORDER BY genome_hash, run_id, agent_id, fold",
                (dataset_hash,),
            )
            records = cursor.fetchall()
        return tuple(
            CandidateRow(
                dataset_hash=_as_str(record[0]),
                genome_hash=_as_str(record[1]),
                agent_id=_as_str(record[2]),
                run_id=_as_str(record[3]),
                fold=_as_str(record[4]),
                skill_lb_micro=_as_int(record[5]),
                pnl_lb_cents=_as_int(record[6]),
            )
            for record in records
        )

    def __iter__(self) -> Iterator[RunRow]:
        return iter(self.runs())

    def __repr__(self) -> str:
        return f"RunStore(path={self._path.as_posix()!r})"
