"""The showcase pack: landmark events kept apart rather than thrown away (7.1, 5.6, ruling R264).

Decision D-S5. The v1 demo pack holds twelve markets and stays exactly where it is, as the migration
identity of 7.10. The **showcase pack** is a second showcase dataset: sealed, ``purpose: "showcase"``, a
few dozen landmark markets, and carrying **the same depth of bars, trades, news and as-of stamps as a
research market** wherever a real tape survives in the Wayback archive or in Manifold's history. The last
clause is the whole point of the ruling: a showcase whose data is shallower than the research data teaches
the wrong lesson about the product, and a demo that is visibly a demo is worse than no demo.

**What the v1 pack actually carries, measured rather than assumed.** Its twelve markets hold between 4
and 361 daily bars, ``n_trades = 0`` and ``traded_bars = 0`` on every one of them, and ``data/demo_v1``
has **no news directory at all**. So not one v1 market clears the depth bar of ruling R264, and eleven of
the twelve fail it on news alone while the twelfth (the Titan submersible market, four bars over a
three-day life) fails it on bars as well. That is why every row of :data:`SHOWCASE_LANDMARKS` reads
``sourced = False`` today and why the eleven that carry a usable bar tape say so in ``bars_available``:
the pack is a real tape short, and the honest form of that is a table that names the gap per row.

**A showcase dataset is exempt from the window rule of 5.6 and from nothing else** (ruling R263). It
seals, loads and replays like any other dataset and ``run_backtest`` runs it, but it is never the source
of a fold, a fitness value, a rule promotion, an insight or a claim, and a memory or hive carried forward
from a run on one is refused too (ruling R291). :func:`refuse_if_showcase` is the one spelling of that
refusal, so the callers of 5.6 raise the same error with the same message.

**What this module is, and what it is not yet.** It is the plan and the machinery: the landmark table,
the sourcing state of each row, the build config a showcase build runs under, the depth bar a sourced
market has to clear, and the ``notes`` entry that documents what could not be sourced. It fetches
nothing: every row names the archive a later networked lot must read it from, and
:func:`unsourced_landmarks` is the list that lot works through. Building the pack without that lot would
mean inventing a tape, and an invented tape in a showcase is a lie told with a chart.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from pmx.errors import InvalidConfigError, ShowcaseDatasetError
from pmx.types import PURPOSE_SHOWCASE, PURPOSES, WINDOW_DAYS_MAX, BuildConfig

__all__ = [
    "SHOWCASE_BARS_MIN",
    "SHOWCASE_LANDMARKS",
    "SHOWCASE_MARKETS_MIN",
    "SHOWCASE_MARKETS_TARGET",
    "SHOWCASE_NAME",
    "SHOWCASE_SOURCES",
    "SOURCE_DEMO_V1",
    "SOURCE_KALSHI_HISTORY",
    "SOURCE_MANIFOLD_HISTORY",
    "SOURCE_WAYBACK",
    "ShowcaseLandmark",
    "ShowcasePlan",
    "check_showcase_depth",
    "landmarks_by_source",
    "landmarks_with_bars",
    "refuse_if_showcase",
    "showcase_build_config",
    "showcase_notes",
    "showcase_plan",
    "sourced_landmarks",
    "unsourced_landmarks",
]

#: The dataset directory name the pack is built into. It is a dataset like any other: its own hash, its
#: own manifest, its own seal, and ``purpose: "showcase"`` in that manifest.
SHOWCASE_NAME: Final = "showcase_v1"

#: "A few dozen markets" (ruling R264), read as a floor of twenty-four: twice the twelve of v1, which is
#: what "grows past the twelve" has to mean if it is to mean anything. The target is the table's length.
SHOWCASE_MARKETS_MIN: Final = 24

#: The depth bar a sourced showcase market clears (ruling R264: a research market's depth). On the daily
#: grid twenty bars is three weeks of tape, which is exactly ``BuildConfig.min_traded_bars``: the number
#: is not a new rule, it is 7.4's, restated here so a showcase market cannot be admitted on a four-bar
#: stub that renders as an empty chart.
SHOWCASE_BARS_MIN: Final = 20

#: Where a landmark's tape can be read from.
SOURCE_WAYBACK: Final = "wayback"
SOURCE_MANIFOLD_HISTORY: Final = "manifold_history"
SOURCE_KALSHI_HISTORY: Final = "kalshi_history"
SOURCE_DEMO_V1: Final = "demo_v1"
SHOWCASE_SOURCES: Final = (SOURCE_WAYBACK, SOURCE_MANIFOLD_HISTORY, SOURCE_KALSHI_HISTORY, SOURCE_DEMO_V1)


@dataclass(frozen=True, slots=True)
class ShowcaseLandmark:
    """One landmark event the pack wants, and the state of its sourcing.

    Deliberately **not** a market. A market carries a resolution, a first price and a tape, and this row
    carries none of them: the resolution is read off the venue's own record by the lot that sources it,
    never written here from memory. What this row carries is the question a reader would recognise, the
    date the event resolved, the archive to read it from, and what is missing.

    ``sourced`` means "in the pack and clearing the depth bar", which is ``False`` on every row today.
    ``bars_available`` means "a bar tape for this event already exists in the repository", which is true
    of eleven v1 markets and is the difference between a row that needs a whole tape and a row that needs
    the news and the prints beside a tape it has. Neither is a to-do marker: both are rendered into the
    manifest's ``notes`` by :func:`showcase_notes`, so a reader of the pack sees which landmarks are in
    it and which the archive would not give up.
    """

    landmark_id: str
    title: str
    question: str
    provider: str
    category: str
    resolved_on: str
    source: str
    source_hint: str
    sourced: bool = False
    bars_available: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        if self.source not in SHOWCASE_SOURCES:
            raise InvalidConfigError(
                "a landmark names one of the four archives",
                landmark_id=self.landmark_id,
                source=self.source,
            )
        if not self.question or not self.title:
            raise InvalidConfigError(
                "a landmark carries a title and a question", landmark_id=self.landmark_id
            )

    @property
    def missing(self) -> tuple[str, ...]:
        """What this row still needs, in the order a sourcing lot would get it.

        A row with a bar tape needs the as-of news and the print tape; a row with nothing needs the bars
        first. The tuple is what :func:`showcase_notes` renders, so the manifest says what is missing per
        landmark rather than reporting one aggregate number that hides which rows are which.
        """
        if self.sourced:
            return ()
        if self.bars_available:
            return ("news", "trades")
        return ("bars", "news", "trades")

    def to_dict(self) -> dict[str, object]:
        return {
            "landmark_id": self.landmark_id,
            "title": self.title,
            "question": self.question,
            "provider": self.provider,
            "category": self.category,
            "resolved_on": self.resolved_on,
            "source": self.source,
            "source_hint": self.source_hint,
            "sourced": self.sourced,
            "bars_available": self.bars_available,
            "missing": list(self.missing),
            "note": self.note,
        }


_V1_NOTE: Final = (
    "The v1 pack carries this market's daily bars and no news and no prints "
    "(data/demo_v1 has no news directory and n_trades is 0 on all twelve markets), "
    "so the row needs the as-of news and the print tape before it enters the pack."
)


#: The landmark table (ruling R264). Every row is a public event with a date a reader can check, and the
#: pack grows past the twelve of v1 by holding forty-one of them. ``source_hint`` is what a networked lot
#: asks for: a Wayback capture of a venue page, a Manifold market history, a Kalshi series. **Nothing
#: here was fetched by this package**, and no row is ``sourced`` yet, for the reason the module docstring
#: measures.
SHOWCASE_LANDMARKS: Final[tuple[ShowcaseLandmark, ...]] = (
    # ---- the twelve events the v1 pack already carries a bar tape for (7.10) -----------------------
    ShowcaseLandmark(
        landmark_id="brexit-2016",
        title="United Kingdom European Union membership referendum",
        question="Will the UK vote to leave the EU in the June 2016 referendum?",
        provider="demo",
        category="politics",
        resolved_on="2016-06-24",
        source=SOURCE_DEMO_V1,
        source_hint="data/demo_v1/markets/demo-brexit-2016.json, 145 bars",
        bars_available=True,
        note=_V1_NOTE,
    ),
    ShowcaseLandmark(
        landmark_id="us-presidential-2016",
        title="United States presidential election, 2016",
        question="Will Donald Trump win the 2016 US presidential election?",
        provider="demo",
        category="politics",
        resolved_on="2016-11-09",
        source=SOURCE_DEMO_V1,
        source_hint="data/demo_v1/markets/demo-trump-2016.json, 162 bars",
        bars_available=True,
        note=_V1_NOTE,
    ),
    ShowcaseLandmark(
        landmark_id="us-presidential-2024",
        title="United States presidential election, 2024",
        question="Will Donald Trump win the 2024 US presidential election?",
        provider="demo",
        category="politics",
        resolved_on="2024-11-06",
        source=SOURCE_DEMO_V1,
        source_hint="data/demo_v1/markets/demo-trump-2024.json, 129 bars",
        bars_available=True,
        note=_V1_NOTE,
    ),
    ShowcaseLandmark(
        landmark_id="bitcoin-60k-2021",
        title="Bitcoin above sixty thousand dollars",
        question="Will Bitcoin trade above $60,000 at any point during 2021?",
        provider="demo",
        category="crypto",
        resolved_on="2021-04-14",
        source=SOURCE_DEMO_V1,
        source_hint="data/demo_v1/markets/demo-btc-60k-2021.json, 100 bars",
        bars_available=True,
        note=_V1_NOTE,
    ),
    ShowcaseLandmark(
        landmark_id="bitcoin-100k-2022",
        title="Bitcoin fails to reach one hundred thousand dollars in 2022",
        question="Will Bitcoin reach $100,000 by the end of 2022?",
        provider="demo",
        category="crypto",
        resolved_on="2022-12-31",
        source=SOURCE_DEMO_V1,
        source_hint="data/demo_v1/markets/demo-btc-100k-2022.json, 361 bars",
        bars_available=True,
        note=_V1_NOTE,
    ),
    ShowcaseLandmark(
        landmark_id="ethereum-merge-2022",
        title="Ethereum transition to proof of stake",
        question="Will Ethereum complete the Merge to proof of stake in 2022?",
        provider="demo",
        category="crypto",
        resolved_on="2022-09-15",
        source=SOURCE_DEMO_V1,
        source_hint="data/demo_v1/markets/demo-eth-merge-2022.json, 168 bars",
        bars_available=True,
        note=_V1_NOTE,
    ),
    ShowcaseLandmark(
        landmark_id="fed-hike-march-2022",
        title="First Federal Reserve rate rise of the 2022 cycle",
        question="Will the US Federal Reserve raise rates at its March 2022 meeting?",
        provider="demo",
        category="economics",
        resolved_on="2022-03-16",
        source=SOURCE_DEMO_V1,
        source_hint="data/demo_v1/markets/demo-fed-hike-mar-2022.json, 71 bars",
        bars_available=True,
        note=_V1_NOTE,
    ),
    ShowcaseLandmark(
        landmark_id="us-recession-2023",
        title="The recession that did not arrive in 2023",
        question="Will the US enter a recession (two negative GDP quarters) in 2023?",
        provider="demo",
        category="economics",
        resolved_on="2023-12-31",
        source=SOURCE_DEMO_V1,
        source_hint="data/demo_v1/markets/demo-us-recession-2023.json, 356 bars",
        bars_available=True,
        note=_V1_NOTE,
    ),
    ShowcaseLandmark(
        landmark_id="gpt4-release-2023",
        title="Release of GPT-4",
        question="Will OpenAI release GPT-4 during 2023?",
        provider="demo",
        category="tech",
        resolved_on="2023-03-14",
        source=SOURCE_DEMO_V1,
        source_hint="data/demo_v1/markets/demo-gpt4-2023.json, 64 bars",
        bars_available=True,
        note=_V1_NOTE,
    ),
    ShowcaseLandmark(
        landmark_id="lk99-2023",
        title="The LK-99 superconductor claim",
        question="Will LK-99 be confirmed as a room-temperature ambient-pressure superconductor?",
        provider="demo",
        category="science",
        resolved_on="2023-08-31",
        source=SOURCE_DEMO_V1,
        source_hint="data/demo_v1/markets/demo-lk99-superconductor-2023.json, 37 bars",
        bars_available=True,
        note=_V1_NOTE,
    ),
    ShowcaseLandmark(
        landmark_id="fifa-world-cup-2022",
        title="FIFA World Cup, 2022",
        question="Will Argentina win the 2022 FIFA World Cup?",
        provider="demo",
        category="sports",
        resolved_on="2022-12-18",
        source=SOURCE_DEMO_V1,
        source_hint="data/demo_v1/markets/demo-argentina-wc-2022.json, 30 bars",
        bars_available=True,
        note=_V1_NOTE,
    ),
    ShowcaseLandmark(
        landmark_id="titan-submersible-2023",
        title="Loss of the Titan submersible",
        question="Will the Titan submersible be found intact with survivors (June 2023)?",
        provider="demo",
        category="other",
        resolved_on="2023-06-22",
        source=SOURCE_DEMO_V1,
        source_hint="data/demo_v1/markets/demo-titan-sub-found-2023.json, 4 bars",
        bars_available=False,
        note=(
            "The one v1 market that fails the depth bar on bars as well as on news: four daily bars "
            "over a three-day life. A three-day event is a real landmark and a four-bar chart is not a "
            "showcase, so this row needs an hourly or minute tape from the archive, not the daily one."
        ),
    ),
    # ---- the landmarks a networked lot must read out of an archive ---------------------------------
    ShowcaseLandmark(
        landmark_id="scottish-referendum-2014",
        title="Scottish independence referendum",
        question="Will Scotland vote for independence in the September 2014 referendum?",
        provider="demo",
        category="politics",
        resolved_on="2014-09-19",
        source=SOURCE_WAYBACK,
        source_hint="web.archive.org captures of the 2014 referendum market pages",
        note="A 2014 tape predates every venue this repository imports from.",
    ),
    ShowcaseLandmark(
        landmark_id="us-presidential-2020",
        title="United States presidential election, 2020",
        question="Will Joe Biden win the 2020 US presidential election?",
        provider="demo",
        category="politics",
        resolved_on="2020-11-07",
        source=SOURCE_WAYBACK,
        source_hint="web.archive.org captures of the 2020 presidential market pages",
    ),
    ShowcaseLandmark(
        landmark_id="first-trump-impeachment-2019",
        title="First impeachment of Donald Trump",
        question="Will the House of Representatives impeach Donald Trump before 1 January 2020?",
        provider="demo",
        category="politics",
        resolved_on="2019-12-18",
        source=SOURCE_WAYBACK,
        source_hint="web.archive.org captures of the 2019 impeachment markets",
    ),
    ShowcaseLandmark(
        landmark_id="biden-withdrawal-2024",
        title="Withdrawal of Joe Biden from the 2024 race",
        question="Will Joe Biden be the Democratic nominee for President in 2024?",
        provider="kalshi",
        category="politics",
        resolved_on="2024-08-19",
        source=SOURCE_KALSHI_HISTORY,
        source_hint="Kalshi nominee series and its 2024 event tickers, historical candlestick path",
    ),
    ShowcaseLandmark(
        landmark_id="us-midterms-2022",
        title="United States midterm elections, 2022",
        question="Will the Republican Party win a majority of the US House in the 2022 midterms?",
        provider="kalshi",
        category="politics",
        resolved_on="2022-11-16",
        source=SOURCE_KALSHI_HISTORY,
        source_hint="Kalshi 2022 congressional control series, historical candlestick path",
    ),
    ShowcaseLandmark(
        landmark_id="uk-gilt-crisis-2022",
        title="United Kingdom gilt crisis and the Truss resignation",
        question="Will Liz Truss cease to be Prime Minister before 1 December 2022?",
        provider="manifold",
        category="politics",
        resolved_on="2022-10-20",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the October 2022 United Kingdom markets",
    ),
    ShowcaseLandmark(
        landmark_id="argentina-election-2023",
        title="Argentine general election, 2023",
        question="Will Javier Milei win the 2023 Argentine presidential run-off?",
        provider="manifold",
        category="politics",
        resolved_on="2023-11-19",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the 2023 Argentine election markets",
    ),
    ShowcaseLandmark(
        landmark_id="covid-pandemic-declaration",
        title="World Health Organization pandemic declaration",
        question="Will the WHO declare COVID-19 a pandemic before 1 April 2020?",
        provider="demo",
        category="health",
        resolved_on="2020-03-11",
        source=SOURCE_WAYBACK,
        source_hint="web.archive.org captures of the early 2020 pandemic markets",
    ),
    ShowcaseLandmark(
        landmark_id="bitcoin-20k-2017",
        title="Bitcoin above twenty thousand dollars",
        question="Will Bitcoin trade above $20,000 before 1 January 2018?",
        provider="demo",
        category="crypto",
        resolved_on="2017-12-17",
        source=SOURCE_WAYBACK,
        source_hint="web.archive.org captures of the December 2017 crypto threshold markets",
    ),
    ShowcaseLandmark(
        landmark_id="bitcoin-halving-2024",
        title="Fourth Bitcoin halving",
        question="Will the fourth Bitcoin halving occur before 1 May 2024?",
        provider="manifold",
        category="crypto",
        resolved_on="2024-04-20",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the halving markets of 2024",
    ),
    ShowcaseLandmark(
        landmark_id="ftx-collapse-2022",
        title="Collapse of FTX",
        question="Will FTX file for bankruptcy before 1 December 2022?",
        provider="manifold",
        category="crypto",
        resolved_on="2022-11-11",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the November 2022 exchange markets",
    ),
    ShowcaseLandmark(
        landmark_id="silicon-valley-bank-2023",
        title="Failure of Silicon Valley Bank",
        question="Will a US bank with more than $100 billion in assets fail in March 2023?",
        provider="manifold",
        category="finance",
        resolved_on="2023-03-10",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the March 2023 banking markets",
    ),
    ShowcaseLandmark(
        landmark_id="credit-suisse-2023",
        title="Acquisition of Credit Suisse",
        question="Will Credit Suisse be acquired or resolved before 1 April 2023?",
        provider="manifold",
        category="finance",
        resolved_on="2023-03-19",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the March 2023 banking markets",
    ),
    ShowcaseLandmark(
        landmark_id="gamestop-january-2021",
        title="GameStop short squeeze",
        question="Will GameStop close above $300 before 1 February 2021?",
        provider="demo",
        category="finance",
        resolved_on="2021-01-27",
        source=SOURCE_WAYBACK,
        source_hint="web.archive.org captures of the January 2021 single-equity markets",
    ),
    ShowcaseLandmark(
        landmark_id="nvidia-guidance-may-2023",
        title="Nvidia guidance of May 2023",
        question="Will Nvidia guide above $8 billion for the quarter reported in May 2023?",
        provider="demo",
        category="finance",
        resolved_on="2023-05-24",
        source=SOURCE_WAYBACK,
        source_hint="web.archive.org captures of the 2023 earnings markets",
    ),
    ShowcaseLandmark(
        landmark_id="fed-75bp-june-2022",
        title="Federal Reserve raises rates by seventy-five basis points",
        question="Will the FOMC raise the federal funds rate by 75 basis points in June 2022?",
        provider="kalshi",
        category="economics",
        resolved_on="2022-06-15",
        source=SOURCE_KALSHI_HISTORY,
        source_hint="Kalshi FED series and its June 2022 event tickers",
    ),
    ShowcaseLandmark(
        landmark_id="cpi-91-july-2022",
        title="United States CPI prints nine point one percent",
        question="Will the US year-on-year CPI print above 9 percent for June 2022?",
        provider="kalshi",
        category="economics",
        resolved_on="2022-07-13",
        source=SOURCE_KALSHI_HISTORY,
        source_hint="Kalshi CPIYOY series and its July 2022 event tickers",
    ),
    ShowcaseLandmark(
        landmark_id="debt-ceiling-2023",
        title="United States debt ceiling standoff of 2023",
        question="Will the US debt ceiling be raised or suspended before 1 July 2023?",
        provider="manifold",
        category="economics",
        resolved_on="2023-06-03",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the 2023 debt ceiling markets",
    ),
    ShowcaseLandmark(
        landmark_id="russia-invasion-2022",
        title="Russian invasion of Ukraine",
        question="Will Russia invade Ukraine before 1 March 2022?",
        provider="manifold",
        category="world",
        resolved_on="2022-02-24",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the February 2022 invasion markets",
    ),
    ShowcaseLandmark(
        landmark_id="nord-stream-2022",
        title="Nord Stream pipeline sabotage",
        question="Will the Nord Stream pipelines be damaged before 1 October 2022?",
        provider="manifold",
        category="world",
        resolved_on="2022-09-26",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the September 2022 energy infrastructure markets",
    ),
    ShowcaseLandmark(
        landmark_id="queen-elizabeth-2022",
        title="Death of Elizabeth II",
        question="Will Charles become King of the United Kingdom before 1 January 2023?",
        provider="manifold",
        category="world",
        resolved_on="2022-09-08",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the September 2022 succession markets",
    ),
    ShowcaseLandmark(
        landmark_id="israel-gaza-october-2023",
        title="October 2023 escalation in the Middle East",
        question="Will a ground operation in Gaza begin before 1 November 2023?",
        provider="manifold",
        category="world",
        resolved_on="2023-10-27",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the October 2023 Middle East markets",
    ),
    ShowcaseLandmark(
        landmark_id="openai-board-november-2023",
        title="OpenAI leadership crisis",
        question="Will Sam Altman be chief executive of OpenAI on 1 December 2023?",
        provider="manifold",
        category="tech",
        resolved_on="2023-11-29",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the November 2023 OpenAI markets",
    ),
    ShowcaseLandmark(
        landmark_id="starship-orbit-2024",
        title="Starship reaches orbital velocity",
        question="Will a Starship flight reach orbital velocity before 1 April 2024?",
        provider="manifold",
        category="science",
        resolved_on="2024-03-14",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the Starship flight markets",
    ),
    ShowcaseLandmark(
        landmark_id="artemis-1-2022",
        title="Artemis 1 launch",
        question="Will Artemis 1 launch before 1 December 2022?",
        provider="manifold",
        category="science",
        resolved_on="2022-11-16",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the Artemis 1 launch markets",
    ),
    ShowcaseLandmark(
        landmark_id="hurricane-ian-2022",
        title="Hurricane Ian landfall",
        question="Will a major hurricane make landfall in Florida before 1 November 2022?",
        provider="kalshi",
        category="weather",
        resolved_on="2022-09-28",
        source=SOURCE_KALSHI_HISTORY,
        source_hint="Kalshi hurricane series and its 2022 event tickers",
    ),
    ShowcaseLandmark(
        landmark_id="hottest-year-2023",
        title="Hottest year on record",
        question="Will 2023 be the hottest year on record?",
        provider="manifold",
        category="weather",
        resolved_on="2024-01-12",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the annual temperature record markets",
    ),
    ShowcaseLandmark(
        landmark_id="paris-olympics-2024",
        title="Summer Olympics, 2024",
        question="Will the United States top the 2024 Olympic gold medal table?",
        provider="manifold",
        category="sports",
        resolved_on="2024-08-11",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the 2024 Olympic markets",
    ),
    ShowcaseLandmark(
        landmark_id="oppenheimer-oscars-2024",
        title="Academy Awards, 2024",
        question="Will Oppenheimer win Best Picture at the 2024 Academy Awards?",
        provider="manifold",
        category="entertainment",
        resolved_on="2024-03-11",
        source=SOURCE_MANIFOLD_HISTORY,
        source_hint="Manifold market history for the 2024 Academy Awards markets",
    ),
)

#: The target the table itself sets: every landmark of :data:`SHOWCASE_LANDMARKS`, sourced. It is a
#: derived constant rather than a hand-written number so the two can never disagree.
SHOWCASE_MARKETS_TARGET: Final = len(SHOWCASE_LANDMARKS)


@dataclass(frozen=True, slots=True)
class ShowcasePlan:
    """The pack as a plan: how many landmarks, how many are sourced, and what is missing."""

    landmarks: tuple[ShowcaseLandmark, ...]

    @property
    def n(self) -> int:
        return len(self.landmarks)

    @property
    def n_sourced(self) -> int:
        return sum(1 for row in self.landmarks if row.sourced)

    @property
    def n_with_bars(self) -> int:
        return sum(1 for row in self.landmarks if row.bars_available)

    @property
    def n_unsourced(self) -> int:
        return self.n - self.n_sourced

    @property
    def reaches_floor(self) -> bool:
        """Whether the **sourced** rows reach :data:`SHOWCASE_MARKETS_MIN`.

        False today, and that is the honest answer: not one row is sourced, because the v1 pack carries
        no news and no prints and the rest of the table is an archive read a later lot has to do.
        """
        return self.n_sourced >= SHOWCASE_MARKETS_MIN

    def per_provider(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.landmarks:
            counts[row.provider] = counts.get(row.provider, 0) + 1
        return dict(sorted(counts.items()))

    def per_source(self) -> dict[str, int]:
        counts: dict[str, int] = dict.fromkeys(SHOWCASE_SOURCES, 0)
        for row in self.landmarks:
            counts[row.source] += 1
        return counts

    def to_dict(self) -> dict[str, object]:
        return {
            "name": SHOWCASE_NAME,
            "n": self.n,
            "n_sourced": self.n_sourced,
            "n_with_bars": self.n_with_bars,
            "n_unsourced": self.n_unsourced,
            "markets_min": SHOWCASE_MARKETS_MIN,
            "markets_target": SHOWCASE_MARKETS_TARGET,
            "reaches_floor": self.reaches_floor,
            "per_provider": self.per_provider(),
            "per_source": self.per_source(),
            "landmarks": [row.to_dict() for row in self.landmarks],
        }


def showcase_plan(landmarks: Sequence[ShowcaseLandmark] | None = None) -> ShowcasePlan:
    """The landmark table as a plan, sorted by ``landmark_id`` and refusing a duplicate id.

    The sort is not cosmetic: the plan is rendered into the manifest's ``notes``, which is inside no hash
    but is read by a human, and a list whose order depends on how the table was edited is a list two
    builds disagree about for no reason.
    """
    rows = tuple(SHOWCASE_LANDMARKS if landmarks is None else landmarks)
    ids = [row.landmark_id for row in rows]
    duplicates = sorted({name for name in ids if ids.count(name) > 1})
    if duplicates:
        raise InvalidConfigError("two landmarks share an id", landmark_ids=duplicates)
    return ShowcasePlan(landmarks=tuple(sorted(rows, key=lambda row: row.landmark_id)))


def sourced_landmarks(plan: ShowcasePlan | None = None) -> tuple[ShowcaseLandmark, ...]:
    """The landmarks that are in the pack and clear the depth bar. Empty today."""
    rows = showcase_plan() if plan is None else plan
    return tuple(row for row in rows.landmarks if row.sourced)


def unsourced_landmarks(plan: ShowcasePlan | None = None) -> tuple[ShowcaseLandmark, ...]:
    """The landmarks a later networked lot must source, in the order it should work through them.

    This is the deliverable half of the pack that this package cannot finish: fetching is another lot's,
    and the alternative to naming the gap is a pack whose missing rows look like rows nobody wanted.
    """
    rows = showcase_plan() if plan is None else plan
    return tuple(row for row in rows.landmarks if not row.sourced)


def landmarks_with_bars(plan: ShowcasePlan | None = None) -> tuple[ShowcaseLandmark, ...]:
    """The landmarks whose bar tape is already in the repository: the v1 pack's eleven usable markets."""
    rows = showcase_plan() if plan is None else plan
    return tuple(row for row in rows.landmarks if row.bars_available)


def showcase_notes(plan: ShowcasePlan | None = None) -> str:
    """The manifest's ``notes`` entry ruling R264 asks for: what is in the pack and what is not.

    One line per unsourced landmark, with the archive it is waiting on and what is missing, because "a
    ``notes`` entry documenting what could not be sourced" is the difference between a pack that is
    honest about being partial and a pack that is quietly twelve markets again.
    """
    rows = showcase_plan() if plan is None else plan
    lines = [
        f"showcase pack {SHOWCASE_NAME}: {rows.n} landmark events, {rows.n_sourced} sourced, "
        f"{rows.n_with_bars} with a bar tape already in the repository, {rows.n_unsourced} not sourced "
        f"(floor {SHOWCASE_MARKETS_MIN}, target {SHOWCASE_MARKETS_TARGET})."
    ]
    for row in rows.landmarks:
        if row.sourced:
            continue
        note = f" {row.note}" if row.note else ""
        lines.append(
            f"not sourced: {row.landmark_id} ({row.resolved_on}) needs "
            f"{', '.join(row.missing)} from {row.source}: {row.source_hint}.{note}"
        )
    return "\n".join(lines)


def showcase_build_config(
    freeze_date: str, *, providers: Sequence[str] = ("demo",), **overrides: object
) -> BuildConfig:
    """The ``BuildConfig`` a showcase build runs under (5.6, ruling R263).

    ``purpose = "showcase"`` is the whole difference and it is not a flag that relaxes anything else: the
    freeze check still applies to every file and the quality filters of 7.4 are the research ones. What
    the purpose buys is the exemption from the window rule, which is what lets a 2016 referendum sit in a
    dataset built in 2026 at all.

    ``window_days`` defaults to ``WINDOW_DAYS_MAX`` rather than to 365 because a showcase window is
    meaningless: the exemption means no market is dropped for being old, and a config declaring 365 would
    read as a claim about a window the build does not apply.
    """
    fields: dict[str, object] = {
        "freeze_date": freeze_date,
        "providers": tuple(sorted(set(providers))),
        "purpose": PURPOSE_SHOWCASE,
        "window_days": WINDOW_DAYS_MAX,
    }
    fields.update(overrides)
    if fields.get("purpose") != PURPOSE_SHOWCASE:
        raise ShowcaseDatasetError(
            "a showcase build config is built with purpose showcase and nothing else",
            purpose=fields.get("purpose"),
        )
    return BuildConfig(**fields)  # type: ignore[arg-type]


def check_showcase_depth(
    market_id: str, *, n_bars: int, n_trades: int, n_news: int, traded_bars: int = 0
) -> None:
    """Refuse a showcase market shallower than a research market (ruling R264, ``ShowcaseDatasetError``).

    Three depths, and the reason each is a refusal rather than a warning: a market with fewer than
    :data:`SHOWCASE_BARS_MIN` bars renders as an empty chart, a market with neither prints nor a single
    traded bar carries no execution to show, and a market with no news carries no as-of stamp, which is
    the one property of this repository a showcase exists to demonstrate. A pack that admitted any of the
    three would be the shallow demo the ruling was written against, which is exactly what the v1 pack is:
    every one of its twelve markets fails the news clause and one fails the bar clause too.
    """
    if n_bars < SHOWCASE_BARS_MIN:
        raise ShowcaseDatasetError(
            "a showcase market carries a research market's depth of bars",
            market_id=market_id,
            n_bars=n_bars,
            minimum=SHOWCASE_BARS_MIN,
        )
    if n_trades <= 0 and traded_bars <= 0:
        raise ShowcaseDatasetError(
            "a showcase market carries a print tape or a per-bar size, and this one carries neither",
            market_id=market_id,
            n_trades=n_trades,
            traded_bars=traded_bars,
        )
    if n_news <= 0:
        raise ShowcaseDatasetError(
            "a showcase market carries the as-of news a research market carries",
            market_id=market_id,
            n_news=n_news,
        )


def refuse_if_showcase(purpose: str, *, caller: str) -> None:
    """The one spelling of 5.6's refusal (rulings R263 and R291, ``ShowcaseDatasetError``).

    ``make_folds``, ``run_generation``, ``evolve``, ``claim``, the rule tester and
    ``pmx.features.matrix`` each call this **before reading a market**, and ``run_backtest`` calls it for
    the dataset a carried-forward memory or hive came from. One implementation, so no caller can weaken
    the refusal to a warning, and no flag lifts it: the argument is not that a landmark tape is bad data,
    it is that a 2016 referendum in a research run's calibration bins or hive resolutions is a channel
    from outside the run's own window into its observations.
    """
    if purpose not in PURPOSES:
        raise InvalidConfigError("purpose is research or showcase", purpose=purpose, caller=caller)
    if purpose == PURPOSE_SHOWCASE:
        raise ShowcaseDatasetError(
            "a showcase dataset never feeds a fold, a fitness, a promotion, an insight or a claim",
            caller=caller,
            purpose=purpose,
        )


def landmarks_by_source(
    landmarks: Iterable[ShowcaseLandmark] | None = None,
) -> Mapping[str, tuple[str, ...]]:
    """``{archive: (landmark_id, ...)}`` over the unsourced rows: the work order for the networked lot."""
    rows = SHOWCASE_LANDMARKS if landmarks is None else landmarks
    grouped: dict[str, list[str]] = {}
    for row in rows:
        if row.sourced:
            continue
        grouped.setdefault(row.source, []).append(row.landmark_id)
    return {source: tuple(sorted(ids)) for source, ids in sorted(grouped.items())}
