"""Routinator validated-ROA CSV → ``roadata`` (SPEC.md §4.2).

``cc`` and ``origin_as_cc`` are left NULL here; they are filled by the enrichment step.
"""

import sqlite3
from pathlib import Path

import petl

from rir_netdata.addr import from_prefix
from rir_netdata.sources import Tick, ticking

SRC_COLS = ("origin_as", "prefix", "maxlen", "ta")
OUT_COLS = (*SRC_COLS, "origin_as2", "istart", "iend", "type", "pfxlen", "equiv", "equiv2")


def origin_as2(origin_as: str) -> str:
    """Numeric part of an ``AS<n>`` origin (``AS28000`` → ``28000``)."""
    return origin_as[2:] if origin_as[:2].upper() == "AS" else origin_as


def _derive(row) -> tuple:
    res = from_prefix(row.prefix)
    derived = (res.istart, res.iend, res.type, res.pfxlen, res.equiv, res.equiv2)
    return (*row, origin_as2(row.origin_as), *derived)


def table(path: Path) -> petl.Table:
    """Lazy petl table of ``roadata`` rows (the CSV header row is skipped)."""
    return petl.rowmap(
        petl.fromcsv(str(path), encoding="utf-8").skip(1).pushheader(list(SRC_COLS)),
        _derive,
        header=list(OUT_COLS),
    )


def load(conn: sqlite3.Connection, path: Path, tick: Tick | None = None) -> int:
    """Append the ROA export to ``roadata``; return the number of rows loaded."""
    before = conn.execute("SELECT count(*) FROM roadata").fetchone()[0]
    petl.appenddb(ticking(table(path), tick), conn, "roadata", commit=False)
    return conn.execute("SELECT count(*) FROM roadata").fetchone()[0] - before
