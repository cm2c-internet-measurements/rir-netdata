"""Orchestrates a run: download every requested source, then build the db atomically."""

import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from rich.console import Console
from rich.table import Table

from rir_netdata import __version__, db, enrich, export, progress, rov
from rir_netdata.config import Config
from rir_netdata.fetch import Fetched, fetch, make_client
from rir_netdata.sources import Tick, aspa, delegated, riswhois, rpki

# A loader appends one downloaded file to its table(s), reporting progress through the Tick, and
# returns one (meta.source, source serial, rows loaded) per table it filled.
Loaded = tuple[str, str | None, int]
Loader = Callable[[sqlite3.Connection, Path, Tick], list[Loaded]]


class Source(StrEnum):
    all = "all"
    delegated = "delegated"
    rpki = "rpki"
    riswhois = "riswhois"


@dataclass(frozen=True)
class Job:
    name: str  # shown in progress; meta.source comes from the loader
    tables: tuple[str, ...]
    url: str
    cache_name: str
    max_age: int
    load: Loader


def _load_delegated(name: str) -> Loader:
    def load(conn: sqlite3.Connection, path: Path, tick: Tick) -> list[Loaded]:
        pre, n = delegated.load(conn, path, tick)
        return [(name, pre.serial, n)]

    return load


def _load_rpki(conn: sqlite3.Connection, path: Path, tick: Tick) -> list[Loaded]:
    """One Routinator export feeds roadata (ROAs) and aspadata/aspa_providers (ASPAs)."""
    data = rpki.read(path)
    serial = rpki.serial(data)
    roas = rpki.load_roas(conn, data["roas"], tick)
    aspas = aspa.load(conn, data.get("aspas") or [], tick)
    return [("rpki-roas", serial, roas), ("rpki-aspas", serial, aspas)]


def _load_riswhois(name: str) -> Loader:
    return lambda conn, path, tick: [(name, None, riswhois.load(conn, path, tick))]


def plan(cfg: Config, source: Source, rirs: list[str]) -> list[Job]:
    jobs = []
    if source in (Source.all, Source.delegated):
        jobs += [
            Job(
                f"delegated-{rir}",
                ("numres",),
                cfg.delegated[rir],
                f"delegated-{rir}-extended-latest",
                cfg.freshness_seconds.delegated,
                _load_delegated(f"delegated-{rir}"),
            )
            for rir in rirs
        ]
    if source in (Source.all, Source.rpki):
        jobs.append(
            Job(
                "rpki",
                ("roadata", "aspadata", "aspa_providers"),
                cfg.rpki["url"],
                "rpki-routinator.json",
                cfg.freshness_seconds.rpki,
                _load_rpki,
            )
        )
    if source in (Source.all, Source.riswhois):
        jobs += [
            Job(
                f"riswhois-{family}",
                ("riswhois",),
                cfg.riswhois[family],
                f"riswhoisdump.{family.replace('ip', 'IP')}.gz",
                cfg.freshness_seconds.riswhois,
                _load_riswhois(f"riswhois-{family}"),
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
) -> tuple[list[db.MetaRow], Counter[str] | None]:
    tables = list(dict.fromkeys(t for j in jobs for t in j.tables))
    rov_stats = None
    for table in tables:
        db.create_table(conn, table)

    meta = []
    with progress.rows(console) as bars:
        for job, got in zip(jobs, fetched, strict=True):
            with progress.task(bars, f"load {job.name}", progress.count_lines(got.path)) as tick:
                loaded = job.load(conn, got.path, tick)
            meta += [
                db.MetaRow(
                    source,
                    got.url,
                    got.fetched_at_utc,
                    serial,
                    rows,
                    got.sha256,
                    __version__,
                    started,
                )
                for source, serial, rows in loaded
            ]

        for table in (t for t in tables if t in db.INDEXES):
            with progress.task(bars, f"index {table}", 1) as tick:
                db.create_indexes(conn, table)
                tick(1)

        if "roadata" in tables:  # with aspadata: both come from the rpki source
            if not enrich.count(conn, "aspadata"):
                console.print(
                    "[yellow]warning:[/] no ASPAs in the Routinator export; aspadata is empty"
                )
            if "numres" in tables:
                with progress.task(bars, "enrich roadata cc", enrich.count(conn)) as tick:
                    enrich.run(conn, tick)
                total = enrich.count(conn, "aspadata")
                with progress.task(bars, "enrich aspadata asid_cc", total) as tick:
                    enrich.run_aspa(conn, tick)
            else:
                console.print(
                    "[yellow]warning:[/] numres not in this run; roadata.cc, "
                    "roadata.origin_as_cc and aspadata.asid_cc left NULL"
                )

        if "riswhois" in tables:
            if "roadata" in tables:
                with progress.task(bars, "index ROAs", rov.count(conn, "roadata")) as tick:
                    idx = rov.load_index(conn, tick)
                with progress.task(bars, "validate riswhois", rov.count(conn, "riswhois")) as tick:
                    rov_stats = rov.run(conn, idx, tick)
            else:
                console.print(
                    "[yellow]warning:[/] roadata not in this run; riswhois.rovstatus, "
                    "rovreason and rov_roas left NULL"
                )

    db.write_meta(conn, meta)
    return meta, rov_stats


def export_dir(target: Path) -> Path:
    """Exports of ``var/netdata-YYYYMMDD.db`` go in ``var/netdata-YYYYMMDD/``."""
    return target.with_suffix("")


def write_exports(
    conn: sqlite3.Connection, formats: list[export.Format], stage: export.Stage, console: Console
) -> None:
    """Stage the typed exports (everything but ``sqlite.gz``, see ``write_db_gz``)."""
    if not export.TYPED.intersection(formats):
        return
    with progress.rows(console) as bars:
        bad = export.run(
            conn,
            formats,
            stage.path,
            stage.final.name,
            lambda description, total: progress.task(bars, description, total),
        )
    for table, n in bad.items():
        console.print(
            f"[yellow]warning:[/] {table}: {n:,} values didn't fit their type; exported as NULL"
        )


def write_db_gz(db_path: Path, stage: export.Stage, console: Console) -> None:
    """Stage ``<stem>.db.gz``; ``db_path`` must be the finished, closed database file."""
    with progress.rows(console) as bars:
        export.gzip_db(
            db_path, stage, lambda description, total: progress.task(bars, description, total)
        )


def publish_exports(
    formats: list[export.Format], db_path: Path, stage: export.Stage, console: Console
) -> list[Path]:
    """Finish the staged exports of the closed ``db_path`` and publish them, all or nothing."""
    if export.Format.sqlite_gz in formats:
        write_db_gz(db_path, stage, console)
    return stage.publish()


def print_exports(console: Console, stage: export.Stage, published: list[Path]) -> None:
    parts = [str(p) for p in published if p.parent != stage.final]
    inside = [p.name for p in published if p.parent == stage.final]
    if inside:
        parts.append(f"{stage.final}/: {', '.join(inside)}")
    console.print(f"[bold]exports[/] {'; '.join(parts)}")


def run(
    cfg: Config,
    source: Source,
    rirs: list[str],
    target: Path,
    console: Console,
    formats: list[export.Format] | None = None,
) -> Path:
    """Run the pipeline. Nothing is written unless every step, exports included, succeeds."""
    started = datetime.now(UTC)
    jobs = plan(cfg, source, rirs)

    console.rule("[bold]Downloading")
    fetched = _download_all(cfg, jobs, console)

    console.rule("[bold]Building database")
    stage = export.Stage(export_dir(target)) if formats else None
    published = False
    try:
        with db.build(target) as conn:
            meta, rov_stats = _build(conn, jobs, fetched, _iso(started), console)
            if stage:
                console.rule("[bold]Exporting")
                write_exports(conn, formats, stage, console)
        published = True
        if stage:
            exported = publish_exports(formats, target, stage, console)
    except BaseException:
        if stage:
            stage.discard()
        if published:  # the db made it but its exports didn't: take the db back
            target.unlink(missing_ok=True)
        raise

    _summary(console, meta, target, rov_stats)
    if stage:
        print_exports(console, stage, exported)
    return target


def _summary(
    console: Console, meta: list[db.MetaRow], target: Path, rov_stats: Counter[str] | None
) -> None:
    t = Table(title=f"[bold]{target}", title_justify="left")
    t.add_column("source", style="cyan")
    t.add_column("rows", justify="right")
    t.add_column("serial", style="dim")
    for m in meta:
        t.add_row(m.source, f"{m.row_count:,}", m.source_serial or "")
    console.print(t)
    if rov_stats:
        total = sum(rov_stats.values())
        parts = ", ".join(
            f"{s} {rov_stats[s]:,} ({rov_stats[s] / total:.1%})"
            for s in (rov.VALID, rov.INVALID, rov.NOTFOUND)
        )
        console.print(f"[bold]ROV[/] riswhois: {parts}")
