"""Routinator JSON ``aspas`` → ``aspadata`` and ``aspa_providers`` (SPEC.md §4.6).

Each ASPA becomes one ``aspadata`` row (the customer AS and its providers as sorted,
comma-separated AS numbers) and one ``aspa_providers`` row per provider, for joins. AS0 as a
provider ("declares no providers") is kept as published. ``asid_cc`` is left NULL here; it is
filled by the enrichment step.
"""

import re
import sqlite3
from collections.abc import Iterator
from typing import Any

import petl

from rir_netdata.sources import Tick, ticking
from rir_netdata.sources.rpki import FormatError

ASPA_COLS = ("asid", "providers", "ta")
PROVIDER_COLS = ("asid", "provider", "ta")

_AS = re.compile(r"AS(\d+)", re.I)


def asn(value: Any) -> int:
    """``AS43`` → 43. Routinator always writes this form; anything else is a format change."""
    if isinstance(value, str) and (m := _AS.fullmatch(value)):
        return int(m[1])
    raise FormatError(f"unexpected AS number {value!r} in Routinator 'aspas'")


def parse(aspas: list[dict[str, Any]]) -> Iterator[tuple[int, list[int], str]]:
    """(customer AS, providers sorted ascending, trust anchor) per ASPA, in Routinator's order."""
    for a in aspas:
        try:
            customer, providers, ta = a["customer"], a["providers"], a["ta"]
        except (KeyError, TypeError) as e:
            raise FormatError(f"malformed entry in Routinator 'aspas': {a!r}") from e
        yield asn(customer), sorted(asn(p) for p in providers), ta


def load(conn: sqlite3.Connection, aspas: list[dict[str, Any]], tick: Tick | None = None) -> int:
    """Append ASPAs to ``aspadata`` and ``aspa_providers``; return the number of ASPAs loaded."""
    parsed = list(parse(aspas))
    rows = [(c, ",".join(map(str, ps)), ta) for c, ps, ta in parsed]
    pairs = [(c, p, ta) for c, ps, ta in parsed for p in ps]
    before = conn.execute("SELECT count(*) FROM aspadata").fetchone()[0]
    petl.appenddb(ticking(petl.wrap([ASPA_COLS, *rows]), tick), conn, "aspadata", commit=False)
    petl.appenddb(petl.wrap([PROVIDER_COLS, *pairs]), conn, "aspa_providers", commit=False)
    return conn.execute("SELECT count(*) FROM aspadata").fetchone()[0] - before
