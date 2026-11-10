import sqlite3
from pathlib import Path

import pytest

from rir_netdata import db
from rir_netdata.sources import riswhois

FIXTURES = Path(__file__).parent / "fixtures"
V4 = FIXTURES / "riswhoisdump.IPv4.gz"
V6 = FIXTURES / "riswhoisdump.IPv6.gz"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.create_table(c, "riswhois")
    yield c
    c.close()


def test_comments_and_blank_lines_skipped(conn):
    assert riswhois.load(conn, V4) == 5
    junk = "origin_as LIKE '%\\%%' ESCAPE '\\' OR origin_as = '' OR prefix IS NULL"
    assert conn.execute(f"SELECT count(*) FROM riswhois WHERE {junk}").fetchone()[0] == 0


def test_both_families_into_one_table(conn):
    n = riswhois.load(conn, V4) + riswhois.load(conn, V6)
    types = dict(conn.execute("SELECT type, count(*) FROM riswhois GROUP BY type").fetchall())
    assert types == {"ipv4": 5, "ipv6": n - 5}


def test_ipv4_row(conn):
    riswhois.load(conn, V4)
    r = dict(conn.execute("SELECT * FROM riswhois WHERE prefix = '15.0.64.0/18'").fetchone())
    del r["id"]
    assert r == {
        "origin_as": "{13979}",
        "prefix": "15.0.64.0/18",
        "viewed_by": 307,
        "istart": 251674624,
        "iend": 251691007,
        "type": "ipv4",
        "pfxlen": 18,
    }


def test_ipv6_default_route_outside_global_unicast(conn):
    riswhois.load(conn, V6)
    r = conn.execute("SELECT * FROM riswhois WHERE prefix = '::/0' LIMIT 1").fetchone()
    assert (r["istart"], r["iend"], r["pfxlen"]) == (0, 0, 0)


def test_ipv6_row(conn):
    riswhois.load(conn, V6)
    r = conn.execute("SELECT * FROM riswhois WHERE prefix = '2800:22::/32'").fetchone()
    assert (r["origin_as"], r["istart"], r["iend"], r["pfxlen"]) == (
        "7908",
        0x2800002200000000,
        0x28000022FFFFFFFF,
        32,
    )
