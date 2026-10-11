from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from .models import BackupType, DatabaseConfig


class AdapterError(RuntimeError):
    pass


class DatabaseAdapter(ABC):
    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config

    @abstractmethod
    def test_connection(self) -> None: ...

    @abstractmethod
    def backup(self, destination: Path, backup_type: BackupType) -> None: ...

    @abstractmethod
    def restore(self, source: Path, selective: list[str] | None = None) -> None: ...


class SQLiteAdapter(DatabaseAdapter):
    def test_connection(self) -> None:
        try:
            with sqlite3.connect(self.config.database) as connection:
                connection.execute("PRAGMA quick_check")
        except sqlite3.Error as exc:
            raise AdapterError(f"SQLite connection failed: {exc}") from exc

    def backup(self, destination: Path, backup_type: BackupType) -> None:
        if backup_type != "full":
            raise AdapterError("SQLite adapter currently supports full backups only")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            source = sqlite3.connect(self.config.database)
            target = sqlite3.connect(destination)
            with target:
                source.backup(target)
            target.close()
            source.close()
        except sqlite3.Error as exc:
            raise AdapterError(f"SQLite backup failed: {exc}") from exc

    def restore(self, source: Path, selective: list[str] | None = None) -> None:
        if selective:
            raise AdapterError("SQLite selective restore is not supported by this adapter")
        destination = sqlite3.connect(self.config.database)
        source_connection = sqlite3.connect(source)
        try:
            with destination:
                source_connection.backup(destination)
        finally:
            source_connection.close()
            destination.close()


class CommandAdapter(DatabaseAdapter):
    """Adapter for vendor CLIs; data is streamed to files by the database tool."""

    commands = {
        "mysql": ("mysqldump", "mysql"),
        "postgres": ("pg_dump", "pg_restore"),
        "mongodb": ("mongodump", "mongorestore"),
    }

    def __init__(self, config: DatabaseConfig) -> None:
        super().__init__(config)
        try:
            self.backup_command, self.restore_command = self.commands[config.kind]
        except KeyError as exc:
            raise AdapterError(f"Unsupported database type: {config.kind}") from exc

    def _base_args(self) -> list[str]:
        args: list[str] = []
        if self.config.host:
            args += ["--host", self.config.host]
        if self.config.port:
            args += ["--port", str(self.config.port)]
        if self.config.username:
            args += ["--username", self.config.username]
        return args

    def _run(self, args: list[str], env: dict[str, str] | None = None) -> None:
        try:
            subprocess.run(args, check=True, env=env)
        except FileNotFoundError as exc:
            raise AdapterError(f"Required command is not installed: {args[0]}") from exc
        except subprocess.CalledProcessError as exc:
            raise AdapterError(f"{args[0]} failed with exit code {exc.returncode}") from exc

    def test_connection(self) -> None:
        if self.config.kind == "mysql":
            args = [self.restore_command, *self._base_args(), "--execute", "SELECT 1", self.config.database]
        elif self.config.kind == "postgres":
            args = ["pg_isready", *self._base_args(), "--dbname", self.config.database]
        else:
            args = [self.backup_command, *self._base_args(), "--db", self.config.database, "--archive", os.devnull]
        self._run(args, self._environment())

    def backup(self, destination: Path, backup_type: BackupType) -> None:
        if backup_type != "full":
            raise AdapterError(f"{self.config.kind} adapter currently supports full backups only")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self.config.kind == "mysql":
            args = [self.backup_command, *self._base_args(), self.config.database]
            with destination.open("wb") as output:
                self._run_to_file(args, output)
        elif self.config.kind == "postgres":
            self._run([self.backup_command, *self._base_args(), "--format=custom", "--file", str(destination), self.config.database], self._environment())
        else:
            self._run([self.backup_command, *self._base_args(), "--db", self.config.database, "--archive", str(destination)], self._environment())

    def restore(self, source: Path, selective: list[str] | None = None) -> None:
        if self.config.kind == "mysql":
            if selective:
                raise AdapterError("MySQL selective restore requires table-specific dump files")
            args = [self.restore_command, *self._base_args(), self.config.database]
            with source.open("rb") as input_file:
                self._run_from_file(args, input_file)
        elif self.config.kind == "postgres":
            args = [self.restore_command, *self._base_args(), "--dbname", self.config.database]
            for table in selective or []:
                args += ["--table", table]
            self._run([*args, str(source)], self._environment())
        else:
            args = [self.restore_command, *self._base_args(), "--archive", str(source), "--db", self.config.database]
            for collection in selective or []:
                args += ["--nsInclude", f"{self.config.database}.{collection}"]
            self._run(args, self._environment())

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        if self.config.password:
            if self.config.kind == "mysql":
                environment["MYSQL_PWD"] = self.config.password
            elif self.config.kind == "postgres":
                environment["PGPASSWORD"] = self.config.password
        return environment

    def _run_to_file(self, args: list[str], output: object) -> None:
        try:
            subprocess.run(args, check=True, stdout=output, env=self._environment())
        except FileNotFoundError as exc:
            raise AdapterError(f"Required command is not installed: {args[0]}") from exc
        except subprocess.CalledProcessError as exc:
            raise AdapterError(f"{args[0]} failed with exit code {exc.returncode}") from exc

    def _run_from_file(self, args: list[str], input_file: object) -> None:
        try:
            subprocess.run(args, check=True, stdin=input_file, env=self._environment())
        except FileNotFoundError as exc:
            raise AdapterError(f"Required command is not installed: {args[0]}") from exc
        except subprocess.CalledProcessError as exc:
            raise AdapterError(f"{args[0]} failed with exit code {exc.returncode}") from exc


def adapter_for(config: DatabaseConfig) -> DatabaseAdapter:
    if config.kind == "sqlite":
        return SQLiteAdapter(config)
    return CommandAdapter(config)
