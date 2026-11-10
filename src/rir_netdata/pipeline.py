"""Orchestrates a run: download every requested source, then build the db atomically."""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from rich.console import Console
from rich.table import Table

from rir_netdata import __version__, db, enrich, progress
from rir_netdata.config import Config
from rir_netdata.fetch import Fetched, fetch, make_client
from rir_netdata.sources import Tick, delegated, riswhois, rpki

# A loader appends one downloaded file to its table, reporting progress through the Tick, and
# returns (source serial, rows loaded).
Loader = Callable[[sqlite3.Connection, Path, Tick], tuple[str | None, int]]


class Source(StrEnum):
    all = "all"
    delegated = "delegated"
    rpki = "rpki"
    riswhois = "riswhois"


@dataclass(frozen=True)
class Job:
    name: str  # meta.source
    table: str
    url: str
    cache_name: str
    max_age: int
    load: Loader


def _load_delegated(conn: sqlite3.Connection, path: Path, tick: Tick) -> tuple[str | None, int]:
    pre, n = delegated.load(conn, path, tick)
    return pre.serial, n


def _no_serial(load: Callable[[sqlite3.Connection, Path, Tick], int]) -> Loader:
    """Adapt a loader for sources whose files carry no serial."""
    return lambda conn, path, tick: (None, load(conn, path, tick))


def plan(cfg: Config, source: Source, rirs: list[str]) -> list[Job]:
    jobs = []
    if source in (Source.all, Source.delegated):
        jobs += [
            Job(
                f"delegated-{rir}",
                "numres",
                cfg.delegated[rir],
                f"delegated-{rir}-extended-latest",
                cfg.freshness_seconds.delegated,
                _load_delegated,
            )
            for rir in rirs
        ]
    if source in (Source.all, Source.rpki):
        jobs.append(
            Job(
                "rpki",
                "roadata",
                cfg.rpki["url"],
                "rpki-roas.csv",
                cfg.freshness_seconds.rpki,
                _no_serial(rpki.load),
            )
        )
    if source in (Source.all, Source.riswhois):
        jobs += [
            Job(
                f"riswhois-{family}",
                "riswhois",
                cfg.riswhois[family],
                f"riswhoisdump.{family.replace('ip', 'IP')}.gz",
                cfg.freshness_seconds.riswhois,
                _no_serial(riswhois.load),
            )
            for family in ("ipv4", "ipv6")
        ]
    return jobs


def output_path(output_dir: Path, basename: str, when: datetime) -> Path:
    return output_dir / f"{basename}-{when:%Y%m%d}.db"


def _iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _download_all(cfg: Config, jobs: list[Job], console: Console) -> list[Fetched]:
    out = []
    with make_client() as client, progress.downloads(console) as bars:
        for job in jobs:
            got = fetch(
                client,
                job.url,
                cfg.cache_dir / job.cache_name,
                max_age=job.max_age,
                retry_cfg=cfg.retry,
                progress=bars,
            )
            how = "[dim]cached    [/]" if got.from_cache else "[green]downloaded[/]"
            console.print(f"  {how} {job.name}")
            out.append(got)
    return out


def _build(
    conn: sqlite3.Connection,
    jobs: list[Job],
    fetched: list[Fetched],
    started: str,
    console: Console,
) -> list[db.MetaRow]:
    tables = list(dict.fromkeys(j.table for j in jobs))
    for table in tables:
        db.create_table(conn, table)

    meta = []
    with progress.rows(console) as bars:
        for job, got in zip(jobs, fetched, strict=True):
            with progress.task(bars, f"load {job.name}", progress.count_lines(got.path)) as tick:
                serial, rows = job.load(conn, got.path, tick)
            meta.append(
                db.MetaRow(
                    job.name,
                    got.url,
                    got.fetched_at_utc,
                    serial,
                    rows,
                    got.sha256,
                    __version__,
                    started,
                )
            )

        for table in (t for t in tables if t in db.INDEXES):
            with progress.task(bars, f"index {table}", 1) as tick:
                db.create_indexes(conn, table)
                tick(1)

        if "roadata" in tables:
            if "numres" in tables:
                with progress.task(bars, "enrich roadata cc", enrich.count(conn)) as tick:
                    enrich.run(conn, tick)
            else:
                console.print(
                    "[yellow]warning:[/] numres not in this run; roadata.cc and "
                    "roadata.origin_as_cc left NULL"
                )

    db.write_meta(conn, meta)
    return meta


def run(cfg: Config, source: Source, rirs: list[str], target: Path, console: Console) -> Path:
    """Run the pipeline. Nothing is written to ``target`` unless every step succeeds."""
    started = datetime.now(UTC)
    jobs = plan(cfg, source, rirs)

    console.rule("[bold]Downloading")
    fetched = _download_all(cfg, jobs, console)

    console.rule("[bold]Building database")
    with db.build(target) as conn:
        meta = _build(conn, jobs, fetched, _iso(started), console)

    _summary(console, meta, target)
    return target


def _summary(console: Console, meta: list[db.MetaRow], target: Path) -> None:
    t = Table(title=f"[bold]{target}", title_justify="left")
    t.add_column("source", style="cyan")
    t.add_column("rows", justify="right")
    t.add_column("serial", style="dim")
    for m in meta:
        t.add_row(m.source, f"{m.row_count:,}", m.source_serial or "")
    console.print(t)
