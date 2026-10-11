from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class StorageError(RuntimeError):
    pass


def upload(local_path: Path, destination: Path, cloud: str | None = None) -> Path | str:
    if not cloud:
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / local_path.name
        if target.resolve() == local_path.resolve():
            return target
        shutil.copy2(local_path, target)
        return target

    commands = {
        "s3": ["aws", "s3", "cp", str(local_path), f"s3://{destination.as_posix().lstrip('/')}/"],
        "gcs": ["gcloud", "storage", "cp", str(local_path), f"gs://{destination.as_posix().lstrip('/')}/"],
        "azure": ["az", "storage", "blob", "upload", "--file", str(local_path), "--container-name", str(destination)],
    }
    command = commands.get(cloud)
    if command is None:
        raise StorageError(f"Unsupported cloud provider: {cloud}. Use s3, gcs, or azure.")
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise StorageError(f"The {cloud} CLI is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise StorageError(f"Cloud upload failed with exit code {exc.returncode}") from exc
    return f"{cloud}:{destination}"
