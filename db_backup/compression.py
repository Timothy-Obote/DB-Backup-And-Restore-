from __future__ import annotations

import gzip
import shutil
from pathlib import Path


def gzip_file(source: Path, destination: Path | None = None) -> Path:
    destination = destination or source.with_suffix(source.suffix + ".gz")
    with source.open("rb") as input_file, gzip.open(destination, "wb") as output_file:
        shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
    source.unlink()
    return destination


def gunzip_file(source: Path, destination: Path | None = None) -> Path:
    if source.suffix != ".gz":
        return source
    destination = destination or source.with_suffix("")
    with gzip.open(source, "rb") as input_file, destination.open("wb") as output_file:
        shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
    return destination
