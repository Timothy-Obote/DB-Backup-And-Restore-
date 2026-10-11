from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

BackupType = Literal["full", "incremental", "differential"]


@dataclass(frozen=True)
class DatabaseConfig:
    kind: str
    database: str
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None


@dataclass(frozen=True)
class BackupResult:
    backup_path: Path
    started_at: str
    finished_at: str
    elapsed_seconds: float
    compressed: bool


@dataclass(frozen=True)
class StorageConfig:
    destination: Path
    cloud: str | None = None
