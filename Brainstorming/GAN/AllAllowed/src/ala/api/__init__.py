"""The read-only HTTP/WebSocket surface (W12, CONTRACTS section 14).

The API never mutates a match: it reads journals that a run already wrote and projects them exactly as
every metric does, so a report served here matches the live match byte for byte (AC-2). The engine and
the runner are never imported by the API; only the journal, the projection, the metric families, and
the detectors are, and all of those are pure readers of the event stream.
"""

from ala.api.app import create_app

__all__ = ["create_app"]
