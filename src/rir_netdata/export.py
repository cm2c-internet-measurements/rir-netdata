"""Exports of a finished database to other formats (SPEC.md §5.7, issue #7).

Every export goes through one typed CSV per table: Python streams rows out of SQLite, applying
the typed cleanup (empty strings and placeholder dates become NULL, ``orgid`` becomes a string,
…), and writes CSV where an empty field means NULL. The CSVs are the ``csv`` export themselves,
and DuckDB reads them back with explicit column types to write Parquet. This needs no DuckDB
extension and never touches the network.

Exports are staged in a temp directory next to their final place and published only when every
format has been written, so a failure leaves nothing behind (see ``Stage``).
"""

import csv
import shutil
import sqlite3
import tarfile
import tempfile
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

import duckdb

from rir_netdata.sources import Tick

BATCH = 50_000

BIGINT, INTEGER, DOUBLE, VARCHAR = "BIGINT", "INTEGER", "DOUBLE", "VARCHAR"

# The typed schema of every export (SPEC §5.7). Columns not listed here, e.g. from a future or
# a legacy db, are exported as VARCHAR.
SCHEMA: dict[str, dict[str, str]] = {
    "numres": {
        "id": BIGINT,
        "rir": VARCHAR,
        "cc": VARCHAR,
        "type": VARCHAR,
        "block": VARCHAR,
        "length": BIGINT,
        "date": INTEGER,
        "status": VARCHAR,
        "orgid": VARCHAR,
        "istart": BIGINT,
        "iend": BIGINT,
        "prefix": VARCHAR,
        "equiv": BIGINT,
    },
    "roadata": {
        "id": BIGINT,
        "origin_as": VARCHAR,
        "prefix": VARCHAR,
        "maxlen": INTEGER,
        "ta": VARCHAR,
        "origin_as2": BIGINT,
        "istart": BIGINT,
        "iend": BIGINT,
        "type": VARCHAR,
        "pfxlen": INTEGER,
        "equiv": DOUBLE,
        "cc": VARCHAR,
        "origin_as_cc": VARCHAR,
        "equiv2": BIGINT,
    },
    "riswhois": {
        "id": BIGINT,
        "origin_as": VARCHAR,
        "prefix": VARCHAR,
        "viewed_by": INTEGER,
        "istart": BIGINT,
        "iend": BIGINT,
        "type": VARCHAR,
        "pfxlen": INTEGER,
        "rovstatus": VARCHAR,
        "rovreason": VARCHAR,
        "rov_roas": INTEGER,
    },
    "meta": {
        "source": VARCHAR,
        "url": VARCHAR,
        "fetched_at_utc": VARCHAR,
        "source_serial": VARCHAR,
        "row_count": BIGINT,
        "sha256": VARCHAR,
        "tool_version": VARCHAR,
        "run_started_at_utc": VARCHAR,
    },
}
TABLES = tuple(SCHEMA)


class Format(StrEnum):
    parquet = "parquet"
    csv = "csv"


# Agreed in #7 but not implemented yet: format → sub-issue.
PLANNED = {"jsonl": 12, "duckdb": 13, "sqlite.gz": 14}


class ExportError(ValueError):
    pass


def parse_formats(values: list[str]) -> list[Format]:
    """Accept repeated and/or comma-separated values; reject unknown and planned formats."""
    out: list[Format] = []
    for raw in (v.strip() for value in values for v in value.split(",")):
        if not raw:
            continue
        if raw in PLANNED:
            raise ExportError(
                f"export format {raw!r} is planned but not implemented yet (#{PLANNED[raw]})"
            )
        try:
            fmt = Format(raw)
        except ValueError:
            known = ", ".join(f.value for f in Format)
            raise ExportError(f"unknown export format {raw!r} (available: {known})") from None
        if fmt not in out:
            out.append(fmt)
    return out


def _to_int(v):
    if v is None or v == "":
        return None
    return int(v)


def _to_float(v):
    if v is None or v == "":
        return None
    return float(v)


def _to_str(v):
    if v is None or v == "":
        return None
    return str(v)


def _date(v):
    # Delegated files use '' and '00000000' (stored by SQLite as 0) for "no date".
    v = _to_int(v)
    return None if v == 0 else v


CONVERT: dict[str, Callable] = {
    BIGINT: _to_int,
    INTEGER: _to_int,
    DOUBLE: _to_float,
    VARCHAR: _to_str,
}


def columns(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    """Column → export type for ``table`` as it exists in this db."""
    known = SCHEMA.get(table, {})
    return {r[1]: known.get(r[1], VARCHAR) for r in conn.execute(f"PRAGMA table_info({table})")}


def tables(conn: sqlite3.Connection) -> list[str]:
    present = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    return [t for t in TABLES if t in present]


def write_csv(
    conn: sqlite3.Connection, table: str, path: Path, tick: Tick | None = None
) -> tuple[int, int]:
    """Write ``table`` as typed CSV; return (rows written, values that couldn't be converted).

    A value that doesn't fit its column's type can only come from a legacy db (e.g. its
    imported summary lines); it is written as NULL and counted, never silently kept.
    """
    cols = columns(conn, table)
    convs = [_date if (table, c) == ("numres", "date") else CONVERT[t] for c, t in cols.items()]
    names = ", ".join(f'"{c}"' for c in cols)
    rows = bad = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        cur = conn.execute(f"SELECT {names} FROM {table} ORDER BY rowid")
        while batch := cur.fetchmany(BATCH):
            out = []
            for row in batch:
                vals = []
                for conv, v in zip(convs, row, strict=True):
                    try:
                        vals.append(conv(v))
                    except (TypeError, ValueError):
                        vals.append(None)
                        bad += 1
                out.append(vals)
            w.writerows(out)
            rows += len(batch)
            if tick:
                tick(len(batch))
    return rows, bad


def _sql_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def csv_to_parquet(csv_path: Path, cols: dict[str, str], out: Path) -> None:
    struct = "{" + ", ".join(f"{_sql_str(c)}: {_sql_str(t)}" for c, t in cols.items()) + "}"
    with duckdb.connect() as con:
        con.execute(
            f"COPY (SELECT * FROM read_csv({_sql_str(str(csv_path))}, header = true,"
            f" columns = {struct}, nullstr = '', auto_detect = false))"
            f" TO {_sql_str(str(out))} (FORMAT parquet, COMPRESSION zstd)"
        )


def csv_tarball(csvs: list[Path], out: Path) -> None:
    with tarfile.open(out, "w:gz", compresslevel=6) as tar:
        for p in csvs:
            tar.add(p, arcname=p.name)


class Stage:
    """A temp dir next to ``final``: ``publish`` swaps it into place, ``discard`` removes it."""

    def __init__(self, final: Path) -> None:
        self.final = final
        final.parent.mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix=f".{final.name}.", dir=final.parent))
        self.path.chmod(0o755)  # mkdtemp creates 0700; exports are meant to be shared

    def publish(self) -> None:
        if self.final.exists():
            shutil.rmtree(self.final)  # an earlier run of the same day
        self.path.replace(self.final)

    def discard(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def run(
    conn: sqlite3.Connection,
    formats: list[Format],
    stage: Path,
    stem: str,
    task: Callable[[str, int | None], object],
) -> dict[str, int]:
    """Write every requested format into ``stage``; return unconvertible-value counts per table.

    ``task(description, total)`` must return a context manager yielding a Tick (see progress.py).
    """
    work = stage / ".csv"
    work.mkdir()
    csvs, bad = [], {}
    for table in tables(conn):
        path = work / f"{table}.csv"
        total = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        with task(f"export {table}.csv", total) as tick:
            _, bad[table] = write_csv(conn, table, path, tick)
        csvs.append(path)
        if Format.parquet in formats:
            with task(f"export {table}.parquet", 1) as tick:
                csv_to_parquet(path, columns(conn, table), stage / f"{table}.parquet")
                tick(1)
    if Format.csv in formats:
        with task(f"pack {stem}.csv.tar.gz", 1) as tick:
            csv_tarball(csvs, stage / f"{stem}.csv.tar.gz")
            tick(1)
    shutil.rmtree(work)
    return {t: n for t, n in bad.items() if n}
