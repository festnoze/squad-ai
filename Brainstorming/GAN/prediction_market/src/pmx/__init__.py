"""pmx: a deterministic backtest arena and hard optimizer for prediction-market forecasting agents.

Version constants live here and nowhere else (CONTRACTS_V2 section 13.2). ``ENGINE_VERSION`` moves whenever a
journal byte can move for the same inputs; ``CONTRACT_VERSION`` names the document the code is shaped by.
This module carries the docstring and these constants only: no import, no re-export.
"""

__version__ = "2.0.0-dev"
ENGINE_VERSION = "2.0.0"
CONTRACT_VERSION = "2.0"
OBS_VERSION = "obs.v2"
ACTIONS_VERSION = "actions.v2"
JOURNAL_VERSION = "journal.v2"
MARKET_SCHEMA = "market.v2"
NEWS_SCHEMA = "news.v1"
DATASET_SCHEMA = "dataset.v1"
INSTRUMENT_SCHEMA = "instrument.v1"
CASH_EVENT_SCHEMA = "cash_event.v1"
SESSION_CALENDAR_SCHEMA = "session_calendar.v1"
FORECAST_SCHEMA = "forecast.v1"
