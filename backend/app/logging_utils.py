"""Minimal structured logging: one JSON line per event, request-id correlated."""

import json
import logging
import sys
import time
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_SECRET_HINTS = ("key", "token", "secret", "authorization")


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def _scrub(payload: dict) -> dict:
    """Drop anything that looks like a credential before it reaches the log."""
    return {
        k: ("***" if any(h in k.lower() for h in _SECRET_HINTS) else v)
        for k, v in payload.items()
    }


def log_event(event: str, **fields) -> None:
    record = {
        "ts": round(time.time(), 3),
        "event": event,
        "request_id": request_id_var.get(),
        **_scrub(fields),
    }
    logging.getLogger("ctagent").info(json.dumps(record, default=str))
