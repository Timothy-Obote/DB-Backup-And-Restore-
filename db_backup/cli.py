from __future__ import annotations

import argparse
import getpass
import os
import sys
import time
from pathlib import Path

from .adapters import AdapterError, adapter_for
from .logging_utils import configure_logging, log_event
from .models import DatabaseConfig, StorageConfig
from .notifications import notify_slack
from .operations import run_backup, run_restore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Back up and restore databases safely from the command line.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_database_args(command: argparse.ArgumentParser) -> None:
        command.add_argument("--type", choices=["sqlite", "mysql", "postgres", "mongodb"], required=True)
        command.add_argument("--database", required=True, help="SQLite file path or database name")
        command.add_argument("--host")
        command.add_argument("--port", type=int)
        command.add_argument("--username")
        command.add_argument("--password-env", help="Read the password from this environment variable")

    backup = subparsers.add_parser("backup", help="Create and optionally upload a backup")
    add_database_args(backup)
    backup.add_argument("--destination", type=Path, required=True)
    backup.add_argument("--cloud", choices=["s3", "gcs", "azure"])
    backup.add_argument("--backup-type", choices=["full", "incremental", "differential"], default="full")
    backup.add_argument("--no-compress", action="store_true")
    backup.add_argument("--log-file", type=Path)
    backup.add_argument("--slack-webhook-env")
    backup.add_argument("--verbose", action="store_true")

    restore = subparsers.add_parser("restore", help="Restore a backup file")
    add_database_args(restore)
    restore.add_argument("--backup-file", type=Path, required=True)
    restore.add_argument("--select", nargs="*", help="Tables or collections when the adapter supports it")

    test = subparsers.add_parser("test-connection", help="Validate credentials and database access")
    add_database_args(test)

    schedule = subparsers.add_parser("schedule", help="Run a backup repeatedly in this process")
    add_database_args(schedule)
    schedule.add_argument("--destination", type=Path, required=True)
    schedule.add_argument("--every-minutes", type=float, required=True)
    schedule.add_argument("--cloud", choices=["s3", "gcs", "azure"])
    schedule.add_argument("--backup-type", choices=["full", "incremental", "differential"], default="full")
    schedule.add_argument("--no-compress", action="store_true")
    schedule.add_argument("--log-file", type=Path)

    return parser


def database_config(args: argparse.Namespace) -> DatabaseConfig:
    password = os.environ.get(args.password_env) if args.password_env else None
    return DatabaseConfig(args.type, args.database, args.host, args.port, args.username, password)


def execute_backup(args: argparse.Namespace, logger: object) -> None:
    result = run_backup(
        adapter_for(database_config(args)),
        StorageConfig(args.destination, args.cloud),
        args.backup_type,
        not args.no_compress,
        logger,
    )
    print(f"Backup created: {result.backup_path}")
    if args.slack_webhook_env:
        webhook = os.environ.get(args.slack_webhook_env)
        if webhook:
            notify_slack(webhook, f"Database backup completed: {result.backup_path}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "test-connection":
        try:
            adapter_for(database_config(args)).test_connection()
            print("Connection successful")
            return 0
        except AdapterError as exc:
            print(f"Connection failed: {exc}", file=sys.stderr)
            return 1

    logger = configure_logging(getattr(args, "log_file", None), getattr(args, "verbose", False))
    try:
        if args.command == "backup":
            execute_backup(args, logger)
        elif args.command == "restore":
            run_restore(adapter_for(database_config(args)), args.backup_file, args.select)
            log_event(logger, "restore_completed", path=str(args.backup_file), status="success")
            print("Restore completed")
        elif args.command == "schedule":
            while True:
                execute_backup(args, logger)
                time.sleep(args.every_minutes * 60)
        return 0
    except (AdapterError, OSError, RuntimeError) as exc:
        log_event(logger, "operation_failed", error=str(exc), status="failure")
        print(f"Operation failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Schedule stopped")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
