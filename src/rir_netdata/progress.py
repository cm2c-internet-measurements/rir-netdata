"""Rich progress bars shared by the pipeline phases."""

import gzip
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from rir_netdata.sources import Tick


def downloads(console: Console) -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description:<24}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )


def rows(console: Console) -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description:<24}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


@contextmanager
def task(progress: Progress, description: str, total: int | None) -> Iterator[Tick]:
    """Add a task; yield a tick callback; mark it complete on success."""
    tid: TaskID = progress.add_task(description, total=total)
    yield lambda n: progress.advance(tid, n)
    t = progress.tasks[progress.task_ids.index(tid)]
    progress.update(tid, total=t.completed, completed=t.completed)


def count_lines(path: Path) -> int:
    """Line count of a (possibly gzipped) file: an upper bound for the rows it will yield."""
    opener = gzip.open if path.suffix == ".gz" else open
    n = 0
    with opener(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            n += chunk.count(b"\n")
    return n
