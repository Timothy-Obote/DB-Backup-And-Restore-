from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from .adapters import DatabaseAdapter
from .compression import gunzip_file, gzip_file
from .logging_utils import log_event, utc_now
from .models import BackupResult, BackupType, StorageConfig
from .storage import upload


def run_backup(
    adapter: DatabaseAdapter,
    storage: StorageConfig,
    backup_type: BackupType,
    compress: bool,
    logger: object,
) -> BackupResult:
    started_at = utc_now()
    started = time.monotonic()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = storage.destination / f"{adapter.config.kind}_{stamp}.backup"
    log_event(logger, "backup_started", database_type=adapter.config.kind, backup_type=backup_type)
    try:
        adapter.backup(raw_path, backup_type)
        final_path = gzip_file(raw_path) if compress else raw_path
        uploaded = upload(final_path, storage.destination, storage.cloud)
        finished_at = utc_now()
        elapsed = time.monotonic() - started
        log_event(logger, "backup_completed", path=str(uploaded), elapsed_seconds=round(elapsed, 3), status="success")
        return BackupResult(final_path, started_at, finished_at, elapsed, compress)
    except Exception as exc:
        log_event(logger, "backup_failed", error=str(exc), status="failure")
        if raw_path.exists():
            raw_path.unlink()
        raise


def run_restore(adapter: DatabaseAdapter, backup_path: Path, selective: list[str] | None = None) -> None:
    source = gunzip_file(backup_path) if backup_path.suffix == ".gz" else backup_path
    try:
        adapter.restore(source, selective)
    finally:
        if source != backup_path and source.exists():
            source.unlink()
