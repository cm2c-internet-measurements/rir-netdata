"""RIPE RIS whois dumps (IPv4 and IPv6) → ``riswhois`` (SPEC.md §4.3)."""

import sqlite3
from pathlib import Path

import petl

from rir_netdata.addr import from_prefix
from rir_netdata.sources import Tick, ticking

SRC_COLS = ("origin_as", "prefix", "viewed_by")
OUT_COLS = (*SRC_COLS, "istart", "iend", "type", "pfxlen")


def _is_record(row) -> bool:
    return bool(row[0]) and not row[0].startswith("%")


def _derive(row) -> tuple:
    res = from_prefix(row.prefix)
    return (*row, res.istart, res.iend, res.type, res.pfxlen)


def table(path: Path) -> petl.Table:
    """Lazy petl table of ``riswhois`` rows; ``.gz`` files are decompressed transparently."""
    return petl.rowmap(
        petl.fromcsv(str(path), delimiter="\t", header=list(SRC_COLS), encoding="utf-8")
        .select(_is_record)
        .cut(*SRC_COLS),
        _derive,
        header=list(OUT_COLS),
    )


def load(conn: sqlite3.Connection, path: Path, tick: Tick | None = None) -> int:
    """Append one dump to ``riswhois``; return the number of rows loaded."""
    before = conn.execute("SELECT count(*) FROM riswhois").fetchone()[0]
    petl.appenddb(ticking(table(path), tick), conn, "riswhois", commit=False)
    return conn.execute("SELECT count(*) FROM riswhois").fetchone()[0] - before
