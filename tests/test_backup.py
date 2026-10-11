from pathlib import Path
import sqlite3

from db_backup.adapters import SQLiteAdapter
from db_backup.compression import gunzip_file
from db_backup.models import DatabaseConfig, StorageConfig
from db_backup.operations import run_backup, run_restore
from db_backup.logging_utils import configure_logging


def make_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE items (name TEXT)")
        connection.execute("INSERT INTO items VALUES ('first')")


def test_sqlite_backup_compress_and_restore(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    make_database(source)
    archive_dir = tmp_path / "archives"
    logger = configure_logging(None)

    result = run_backup(
        SQLiteAdapter(DatabaseConfig("sqlite", str(source))),
        StorageConfig(archive_dir),
        "full",
        True,
        logger,
    )

    assert result.backup_path.name.endswith(".backup.gz")
    compressed_copy = archive_dir / result.backup_path.name
    restored = tmp_path / "restored.db"
    run_restore(SQLiteAdapter(DatabaseConfig("sqlite", str(restored))), compressed_copy)

    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT name FROM items").fetchone() == ("first",)
