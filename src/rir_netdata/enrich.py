"""Country-code enrichment of ``roadata`` from ``numres`` (SPEC.md §4.4).

For each ROA, ``cc`` comes from the allocated/assigned delegation of the same address family that
contains the ROA's first address, and ``origin_as_cc`` from the one containing its origin ASN.
No match gives ``'ZZ'``. All trust anchors are enriched.

Lookups take the nearest delegation starting at or below the value (one index probe on
``numres_type_range``) and then check that it actually covers the value. That is exact because
allocated/assigned delegations don't overlap within a type; tests/test_enrich.py guards the
query, and the assumption was verified against all five live RIR files (Nov 2026).
"""

import sqlite3

from rir_netdata.sources import Tick

BATCH = 50_000

_LOOKUP = """
    SELECT CASE WHEN n.iend >= {value} THEN n.cc END
    FROM numres AS n
    WHERE n.type = {rtype} AND n.status IN ('allocated', 'assigned') AND n.istart <= {value}
    ORDER BY n.istart DESC
    LIMIT 1
"""

_UPDATE = f"""
    UPDATE roadata SET
        cc = coalesce(({_LOOKUP.format(value="roadata.istart", rtype="roadata.type")}), 'ZZ'),
        origin_as_cc = coalesce((
            {_LOOKUP.format(value="CAST(roadata.origin_as2 AS INTEGER)", rtype="'asn'")}
        ), 'ZZ')
    WHERE id BETWEEN ? AND ?
"""


def count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT count(*) FROM roadata").fetchone()[0]


def run(conn: sqlite3.Connection, tick: Tick | None = None) -> int:
    """Fill ``roadata.cc`` and ``roadata.origin_as_cc``; return the number of ROAs enriched."""
    lo, hi = conn.execute("SELECT min(id), max(id) FROM roadata").fetchone()
    if lo is None:
        return 0
    done = 0
    for start in range(lo, hi + 1, BATCH):
        n = conn.execute(_UPDATE, (start, start + BATCH - 1)).rowcount
        done += n
        if tick:
            tick(n)
    return done
