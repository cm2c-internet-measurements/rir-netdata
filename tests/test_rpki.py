import sqlite3
from pathlib import Path

import pytest

from rir_netdata import db
from rir_netdata.sources import rpki

FIXTURE = Path(__file__).parent / "fixtures" / "rpki.csv.txt"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.create_table(c, "roadata")
    yield c
    c.close()


@pytest.mark.parametrize(
    ("given", "want"), [("AS28000", "28000"), ("as0", "0"), ("AS4200000000", "4200000000")]
)
def test_origin_as2(given, want):
    assert rpki.origin_as2(given) == want


def test_header_row_not_loaded(conn):
    n = rpki.load(conn, FIXTURE)
    assert n == len(FIXTURE.read_text().splitlines()) - 1
    assert conn.execute("SELECT count(*) FROM roadata WHERE origin_as = 'ASN'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM roadata WHERE type LIKE 'bad%'").fetchone()[0] == 0


def test_ipv4_roa(conn):
    rpki.load(conn, FIXTURE)
    r = dict(conn.execute("SELECT * FROM roadata WHERE prefix = '2.152.0.0/22'").fetchone())
    del r["id"]
    assert r == {
        "origin_as": "AS52286",
        "prefix": "2.152.0.0/22",
        "maxlen": 24,
        "ta": "lacnic",
        "origin_as2": "52286",
        "istart": 43515904,
        "iend": 43516927,
        "type": "ipv4",
        "pfxlen": 22,
        "equiv": 4,
        "cc": None,
        "origin_as_cc": None,
    }


def test_ipv6_roa(conn):
    rpki.load(conn, FIXTURE)
    r = conn.execute("SELECT * FROM roadata WHERE origin_as = 'AS22894'").fetchone()
    assert (r["type"], r["pfxlen"], r["equiv"]) == ("ipv6", 48, 0)
    assert r["istart"] == 0x2001120100000000
    assert r["iend"] == 0x200112010000FFFF


def test_every_trust_anchor_kept(conn):
    rpki.load(conn, FIXTURE)
    tas = {r[0] for r in conn.execute("SELECT DISTINCT ta FROM roadata")}
    assert tas == {"afrinic", "apnic", "arin", "lacnic", "ripe"}
