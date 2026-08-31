# Golden journals (owner A09, CONTRACTS section 10)

Three frozen scripted matches and their `blake2b-256` journal hashes. They are
the AC-P1 artefact: `tests/test_determinism.py::test_golden_journal_hashes`
replays each scenario in process and compares both the hash **and the bytes**,
and `::test_golden_hashes_survive_a_fresh_interpreter` reproduces the three
hashes in three fresh subprocesses with `PYTHONHASHSEED` unset, `0` and
`12345`. That subprocess pass is the only place a salted builtin `hash()` or a
set iteration reaching the journal can be caught, because both are stable
inside one process and unstable across two.

| Fixture | Template | Seed | Ticks | Markets | Seats | Why it is here |
|---|---|---|---|---|---|---|
| `election_reference` | election | 20260827 | 48 | 5 | 6 | The reference match: the PRD section 5.7 defaults and the `standard_config` seed. Every market resolves at `T`, so the whole settlement happens in finalisation. |
| `harvest_small` | harvest | 424242 | 24 | 3 | 4 | The smallest legal match, so a regression in a boundary (four seats, three markets, the minimum horizon) is visible. |
| `league_wide` | league | 987654321 | 24 | 4 | 8 | The widest table, and the only one whose world resolves a market **mid match** (`M4` at tick 22), so the P1 step 4 resolution path, its `NewsPublished(origin="resolution")` and its settlement group are inside a golden hash. |

The seats, the information profiles and the baseline rotation of each scenario
are defined once, in `tests/test_match_runner.py` (`REFERENCE`, `SMALL`,
`WIDE`), and every A09 test file builds its match through that one builder.

## Regenerating

Moving a golden hash is a deliberate act and must be justified in the commit
message. Exactly four kinds of change legitimately move one, and each requires
a version bump in the same commit (CONTRACTS section 10):

1. a `MatchConfig` field or default: bump `ENGINE_VERSION`;
2. an event payload or a phase order: bump `ENGINE_VERSION`;
3. a draw algorithm in `pxe.rng`: bump `RNG_ALGORITHM_VERSION` **and**
   `ENGINE_VERSION`;
4. a world or info generation rule: bump that template's `template_version`.

A change to `pxe.runner.observation_builder` is deliberately **not** on that
list: since `obs_hash` left the journal (CONTRACTS section 3.5, decision 11),
the observation renderer cannot move a hash at all.

```python
from tests.test_determinism import regenerate_golden

regenerate_golden()  # rewrites the three .journal.jsonl and the three .hash
```

The journals are written with `encoding="utf-8", newline="\n"`, like every
other journal in this repository (CONTRACTS section 4.2), so the committed
bytes are identical on Linux and on Windows and the CI
`determinism-cross-platform` job can compare them directly.
