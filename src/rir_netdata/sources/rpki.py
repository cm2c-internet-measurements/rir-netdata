"""Routinator JSON (the ``/json`` endpoint) → ``roadata`` (SPEC.md §4.2).

The whole file is parsed with the stdlib: about 0.5 GB peak for the ~90 MB of today's export.
``cc`` and ``origin_as_cc`` are left NULL here; they are filled by the enrichment step.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

import petl

from rir_netdata.addr import from_prefix
from rir_netdata.sources import Tick, ticking

SRC_COLS = ("origin_as", "prefix", "maxlen", "ta")
OUT_COLS = (*SRC_COLS, "origin_as2", "istart", "iend", "type", "pfxlen", "equiv", "equiv2")
JSON_KEYS = ("asn", "prefix", "maxLength", "ta")  # the Routinator name of each SRC_COLS column


class FormatError(ValueError):
    pass


def origin_as2(origin_as: str) -> str:
    """Numeric part of an ``AS<n>`` origin (``AS28000`` → ``28000``)."""
    return origin_as[2:] if origin_as[:2].upper() == "AS" else origin_as


def read(path: Path) -> dict[str, Any]:
    """Parse a Routinator JSON export; fail clearly on anything else (e.g. the old CSV)."""
    try:
        data = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise FormatError(f"{path.name}: not Routinator JSON (the /json endpoint): {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("roas"), list):
        raise FormatError(f"{path.name}: no 'roas' list; expected Routinator JSON (/json)")
    return data


def serial(data: dict[str, Any]) -> str | None:
    """When Routinator generated the export (``metadata.generatedTime``), recorded in ``meta``."""
    return (data.get("metadata") or {}).get("generatedTime")


def _derive(row) -> tuple:
    res = from_prefix(row.prefix)
    derived = (res.istart, res.iend, res.type, res.pfxlen, res.equiv, res.equiv2)
    return (*row, origin_as2(row.origin_as), *derived)


def table(roas: list[dict[str, Any]]) -> petl.Table:
    """Lazy petl table of ``roadata`` rows, in Routinator's order."""
    src = petl.fromdicts(roas, header=list(JSON_KEYS)).setheader(list(SRC_COLS))
    return petl.rowmap(src, _derive, header=list(OUT_COLS))


def load_roas(
    conn: sqlite3.Connection, roas: list[dict[str, Any]], tick: Tick | None = None
) -> int:
    """Append ROAs to ``roadata``; return the number of rows loaded."""
    before = conn.execute("SELECT count(*) FROM roadata").fetchone()[0]
    petl.appenddb(ticking(table(roas), tick), conn, "roadata", commit=False)
    return conn.execute("SELECT count(*) FROM roadata").fetchone()[0] - before
