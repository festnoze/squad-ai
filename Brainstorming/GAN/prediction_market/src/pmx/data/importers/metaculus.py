"""The Metaculus importer: declared, token-gated, and deliberately unbuilt (CONTRACTS_V2 7.12, section 13).

Metaculus is the optional fifth provider. It is worth having eventually (its questions are long-dated and
its community forecast is a strong baseline) but it is not a market: there is no price, no fill and no
money, so nothing in it can carry the trading half of a claim, and its API needs a token no reviewer of
this repository has. D6 composes the importers by name, so the name has to exist and has to fail loudly
rather than return an empty tuple that would silently shrink a dataset.

The signature is the one shape of CONTRACTS_V2 7.12 including the ``interval_min`` extension of ruling
R93, so the day this is built no caller changes.
"""

from __future__ import annotations

import os
from typing import Final

from pmx.data.importers._http import HttpClient
from pmx.errors import NotConfiguredError
from pmx.types import Market

METACULUS_PROVIDER: Final = "metaculus"
METACULUS_BASE_URL: Final = "https://www.metaculus.com/api2"
METACULUS_TOKEN_ENV: Final = "PMX_METACULUS_TOKEN"


def import_metaculus(
    *,
    client: HttpClient,
    window_start_ms: int,
    window_end_ms: int,
    freeze_ms: int,
    limit: int | None = None,
    interval_min: int = 1_440,
) -> tuple[Market, ...]:
    """Raise :class:`NotConfiguredError`: the Metaculus path is declared but not implemented.

    It raises whether or not the token is set, because a token is necessary and not sufficient here: the
    importer itself does not exist yet. Returning an empty tuple instead would make a dataset built with
    ``providers=("metaculus",)`` look merely unlucky.
    """
    raise NotConfiguredError(
        "the Metaculus importer is declared but not built",
        provider=METACULUS_PROVIDER,
        env=METACULUS_TOKEN_ENV,
        token_present=str(bool(os.environ.get(METACULUS_TOKEN_ENV))),
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        freeze_ms=freeze_ms,
        limit=str(limit),
        interval_min=interval_min,
        base_url=client.base_url,
    )
