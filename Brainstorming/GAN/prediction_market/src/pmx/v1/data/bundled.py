"""The bundled demo dataset: real resolved events with real outcomes.

Honesty note, stated once and loudly: the **events and their outcomes are real** and verifiable. The
**price paths are reconstructed**, a plausible trajectory consistent with how each market actually
behaved (the Brexit and Trump 2016 nights really did gap, the 2023 recession really was widely predicted
and never came, LK-99 really did spike and collapse). Every market here carries ``source:
"reconstructed"`` so the UI can flag it, and the importer (:mod:`pmx.data.importer`) produces genuine
``source: "imported"`` tapes from a live provider when a network is available.

The mix is deliberate. Some markets are ones the crowd got right (the Fed hike, the Ethereum Merge),
some are upsets where the price was wrong until late (Brexit, Trump 2016), and some are bubbles that
collapsed (BTC to 100k in 2022, LK-99). That spread is what gives agent selection real signal: an agent
that only ever believes the price cannot win on the upsets, and a contrarian cannot win on the obvious
ones.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

# Each entry: id, question, category, resolved_date, resolution (1=YES/0=NO), notes, and an explicit
# price path as (date, cents) control points. Prices are the YES price in whole cents = implied percent.
_MARKETS: list[dict[str, object]] = [
    {
        "id": "brexit-2016",
        "question": "Will the UK vote to leave the EU in the June 2016 referendum?",
        "category": "politics",
        "resolved_date": "2016-06-24",
        "resolution": 1,
        "notes": "The market priced Remain all spring; Leave was a genuine upset that only gapped in on the night.",
        "prices": [
            ["2016-02-01", 32],
            ["2016-03-15", 34],
            ["2016-04-15", 30],
            ["2016-05-15", 26],
            ["2016-06-10", 28],
            ["2016-06-20", 24],
            ["2016-06-23T20:00", 22],
            ["2016-06-23T23:00", 30],
            ["2016-06-24T01:00", 55],
            ["2016-06-24T03:00", 84],
            ["2016-06-24T06:00", 95],
            ["2016-06-24T08:00", 98],
        ],
    },
    {
        "id": "trump-2016",
        "question": "Will Donald Trump win the 2016 US presidential election?",
        "category": "politics",
        "resolved_date": "2016-11-08",
        "resolution": 1,
        "notes": "An underdog the whole race; the price only crossed 50 late on election night.",
        "prices": [
            ["2016-06-01", 25],
            ["2016-08-01", 22],
            ["2016-09-15", 30],
            ["2016-10-08", 16],
            ["2016-11-01", 35],
            ["2016-11-07", 34],
            ["2016-11-08T20:00", 30],
            ["2016-11-08T23:00", 62],
            ["2016-11-09T01:00", 88],
            ["2016-11-09T03:00", 97],
        ],
    },
    {
        "id": "fed-hike-mar-2022",
        "question": "Will the US Federal Reserve raise rates at its March 2022 meeting?",
        "category": "economics",
        "resolved_date": "2022-03-16",
        "resolution": 1,
        "notes": "Well telegraphed; the market was correctly confident throughout.",
        "prices": [
            ["2022-01-05", 55],
            ["2022-01-26", 65],
            ["2022-02-10", 78],
            ["2022-02-24", 72],
            ["2022-03-01", 85],
            ["2022-03-10", 94],
            ["2022-03-15", 97],
        ],
    },
    {
        "id": "btc-60k-2021",
        "question": "Will Bitcoin trade above $60,000 at any point during 2021?",
        "category": "crypto",
        "resolved_date": "2021-04-14",
        "resolution": 1,
        "notes": "Resolved YES in April 2021; the price climbed steadily as the bull run ran.",
        "prices": [
            ["2021-01-05", 30],
            ["2021-01-20", 38],
            ["2021-02-08", 52],
            ["2021-02-20", 66],
            ["2021-03-05", 60],
            ["2021-03-20", 72],
            ["2021-04-05", 85],
            ["2021-04-13", 93],
        ],
    },
    {
        "id": "eth-merge-2022",
        "question": "Will Ethereum complete the Merge to proof of stake in 2022?",
        "category": "crypto",
        "resolved_date": "2022-09-15",
        "resolution": 1,
        "notes": "Slipped for years, then landed in September 2022; confidence rose as testnets merged.",
        "prices": [
            ["2022-04-01", 45],
            ["2022-05-15", 40],
            ["2022-06-08", 55],
            ["2022-07-01", 66],
            ["2022-08-11", 82],
            ["2022-09-06", 90],
            ["2022-09-14", 96],
        ],
    },
    {
        "id": "argentina-wc-2022",
        "question": "Will Argentina win the 2022 FIFA World Cup?",
        "category": "sports",
        "resolved_date": "2022-12-18",
        "resolution": 1,
        "notes": "Opened a favourite, crashed after losing to Saudi Arabia, then climbed back through the knockouts.",
        "prices": [
            ["2022-11-19", 18],
            ["2022-11-22", 9],
            ["2022-11-27", 15],
            ["2022-12-03", 22],
            ["2022-12-09", 30],
            ["2022-12-13", 42],
            ["2022-12-18T14:00", 55],
            ["2022-12-18T18:00", 60],
        ],
    },
    {
        "id": "gpt4-2023",
        "question": "Will OpenAI release GPT-4 during 2023?",
        "category": "tech",
        "resolved_date": "2023-03-14",
        "resolution": 1,
        "notes": "Rumoured for months, released in March 2023.",
        "prices": [
            ["2023-01-10", 58],
            ["2023-01-25", 62],
            ["2023-02-10", 70],
            ["2023-02-24", 80],
            ["2023-03-08", 90],
            ["2023-03-13", 96],
        ],
    },
    {
        "id": "btc-100k-2022",
        "question": "Will Bitcoin reach $100,000 by the end of 2022?",
        "category": "crypto",
        "resolved_date": "2022-12-31",
        "resolution": 0,
        "notes": "A popular call at the 2021 top; the market fell to ~16k instead. A bubble that deflated.",
        "prices": [
            ["2022-01-05", 35],
            ["2022-02-15", 30],
            ["2022-04-01", 26],
            ["2022-05-15", 14],
            ["2022-06-20", 6],
            ["2022-08-15", 8],
            ["2022-10-01", 4],
            ["2022-12-01", 2],
        ],
    },
    {
        "id": "us-recession-2023",
        "question": "Will the US enter a recession (two negative GDP quarters) in 2023?",
        "category": "economics",
        "resolved_date": "2023-12-31",
        "resolution": 0,
        "notes": "The consensus expected a recession all year; growth stayed positive. The crowd was wrong.",
        "prices": [
            ["2023-01-10", 58],
            ["2023-02-15", 62],
            ["2023-03-20", 68],
            ["2023-05-01", 60],
            ["2023-06-15", 50],
            ["2023-08-01", 38],
            ["2023-10-01", 24],
            ["2023-12-01", 10],
        ],
    },
    {
        "id": "lk99-superconductor-2023",
        "question": "Will LK-99 be confirmed as a room-temperature ambient-pressure superconductor?",
        "category": "science",
        "resolved_date": "2023-08-31",
        "resolution": 0,
        "notes": "A viral July 2023 hype spike that replications quickly demolished. A textbook bubble.",
        "prices": [
            ["2023-07-26", 12],
            ["2023-07-28", 32],
            ["2023-07-30", 48],
            ["2023-08-01", 52],
            ["2023-08-03", 40],
            ["2023-08-06", 22],
            ["2023-08-10", 9],
            ["2023-08-20", 3],
        ],
    },
    {
        "id": "trump-2024",
        "question": "Will Donald Trump win the 2024 US presidential election?",
        "category": "politics",
        "resolved_date": "2024-11-05",
        "resolution": 1,
        "notes": "A genuine toss-up in the polls that resolved on the night.",
        "prices": [
            ["2024-07-01", 60],
            ["2024-08-05", 44],
            ["2024-09-10", 48],
            ["2024-10-01", 52],
            ["2024-10-20", 58],
            ["2024-11-04", 55],
            ["2024-11-05T20:00", 60],
            ["2024-11-05T23:00", 82],
            ["2024-11-06T02:00", 95],
        ],
    },
    {
        "id": "titan-sub-found-2023",
        "question": "Will the Titan submersible be found intact with survivors (June 2023)?",
        "category": "other",
        "resolved_date": "2023-06-22",
        "resolution": 0,
        "notes": "Hope was priced in during the search; the implosion was confirmed on June 22.",
        "prices": [
            ["2023-06-19", 40],
            ["2023-06-20", 30],
            ["2023-06-21", 22],
            ["2023-06-22T06:00", 18],
            ["2023-06-22T12:00", 8],
            ["2023-06-22T16:00", 2],
        ],
    },
]


def seed_dataset(out_dir: Path) -> int:
    """Write every bundled market as a JSON file under ``out_dir``. Returns the count written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for m in _MARKETS:
        rows = cast("list[list[object]]", m["prices"])
        payload = {
            "id": m["id"],
            "question": m["question"],
            "category": m["category"],
            "source": "reconstructed",
            "resolution": m["resolution"],
            "resolved_date": m["resolved_date"],
            "notes": m["notes"],
            "prices": [{"t": row[0], "price": row[1]} for row in rows],
        }
        (out_dir / f"{m['id']}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )
    return len(_MARKETS)
