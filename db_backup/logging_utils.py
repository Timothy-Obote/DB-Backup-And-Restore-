from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_logging(log_file: Path | None, verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("db_backup")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_file, encoding="utf-8") if log_file else logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


def log_event(logger: logging.Logger, event: str, **fields: object) -> None:
    logger.info(json.dumps({"timestamp": utc_now(), "event": event, **fields}, default=str))
