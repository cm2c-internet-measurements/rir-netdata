import sqlite3

import pytest

from rir_netdata import db, rov
from rir_netdata.addr import from_prefix
from rir_netdata.sources.rpki import origin_as2

ROAS = [
    # origin, prefix, maxlen, ta
    ("AS28000", "200.40.0.0/16", 24, "lacnic"),
    ("AS28001", "200.40.0.0/16", 16, "lacnic"),  # second ROA on the same prefix
    ("AS64500", "203.0.113.0/24", 24, "apnic"),
    ("AS64500", "203.0.113.0/24", 24, "ripe"),  # duplicate under another TA
    ("AS0", "198.51.100.0/24", 32, "arin"),  # AS0: covers, never matches
    ("AS28000", "2800:a0::/32", 48, "lacnic"),
    ("AS65001", "2001:db8:1:1::/64", 128, "ripe"),
    ("AS65002", "2001:db8:1:1:8000::/65", 65, "ripe"),  # longer than /64
]


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    db.create_table(c, "roadata")
    db.create_table(c, "riswhois")
    for origin, prefix, maxlen, ta in ROAS:
        r = from_prefix(prefix)
        c.execute(
            "INSERT INTO roadata (origin_as, prefix, maxlen, ta, origin_as2, istart, iend, type,"
            " pfxlen) VALUES (?,?,?,?,?,?,?,?,?)",
            (origin, prefix, maxlen, ta, origin_as2(origin), r.istart, r.iend, r.type, r.pfxlen),
        )
    yield c
    c.close()


def _validate(conn, routes):
    """Insert (origin, prefix) routes into riswhois, run ROV, return {prefix+origin: verdict}."""
    for origin, prefix in routes:
        r = from_prefix(prefix)
        conn.execute(
            "INSERT INTO riswhois (origin_as, prefix, viewed_by, istart, iend, type, pfxlen)"
            " VALUES (?,?,?,?,?,?,?)",
            (origin, prefix, 100, r.istart, r.iend, r.type, r.pfxlen),
        )
    stats = rov.run(conn, rov.load_index(conn))
    rows = conn.execute("SELECT origin_as, prefix, rovstatus, rovreason, rov_roas FROM riswhois")
    return {f"{o} {p}": (s, why, n) for o, p, s, why, n in rows}, stats


@pytest.mark.parametrize(
    ("origin", "prefix", "want"),
    [
        ("28000", "200.40.0.0/16", ("valid", None, 2)),
        ("28000", "200.40.7.0/24", ("valid", None, 2)),  # within maxlen 24
        ("28001", "200.40.0.0/16", ("valid", None, 2)),  # one of two covering ROAs matches
        ("28001", "200.40.7.0/24", ("invalid", "length", 2)),  # right ASN, beyond maxlen 16
        ("28000", "200.40.7.128/25", ("invalid", "length", 2)),
        ("99999", "200.40.7.0/24", ("invalid", "asn", 2)),
        ("{28000}", "200.40.0.0/16", ("invalid", "as_set", 2)),  # strict: sets never match
        ("{1,2}", "8.8.8.0/24", ("notfound", None, 0)),  # uncovered AS-set
        ("64500", "203.0.113.0/24", ("valid", None, 2)),  # duplicate ROAs both count
        ("0", "198.51.100.0/24", ("invalid", "asn", 1)),  # AS0 ROA never matches, even AS0
        ("64496", "198.51.100.0/25", ("invalid", "asn", 1)),
        ("28000", "200.0.0.0/8", ("notfound", None, 0)),  # less specific than every ROA
        ("28000", "8.8.8.0/24", ("notfound", None, 0)),
        ("174", "0.0.0.0/0", ("notfound", None, 0)),
        ("28000", "2800:a0:1::/48", ("valid", None, 1)),
        ("28000", "2800:a0:1:1::/64", ("invalid", "length", 1)),
        ("65001", "2001:db8:1:1::1/128", ("valid", None, 1)),  # IPv6 longer than /64
        ("65002", "2001:db8:1:1:8000::/65", ("valid", None, 2)),
        ("65002", "2001:db8:1:1::/65", ("invalid", "asn", 1)),  # sibling /65 not covered by it
        ("174", "::/0", ("notfound", None, 0)),
        ("64500", "fc00::/7", ("notfound", None, 0)),
    ],
)
def test_verdicts(conn, origin, prefix, want):
    got, _ = _validate(conn, [(origin, prefix)])
    assert got[f"{origin} {prefix}"] == want


def test_ipv4_never_matches_ipv6(conn):
    # 200.40.0.0 as an int must not collide with an IPv6 network of the same numeric prefix.
    got, _ = _validate(conn, [("28000", "c828::/16")])
    assert got["28000 c828::/16"] == ("notfound", None, 0)


def test_stats(conn):
    _, stats = _validate(
        conn, [("28000", "200.40.0.0/16"), ("1", "200.40.0.0/16"), ("1", "8.8.8.0/24")]
    )
    assert stats == {"valid": 1, "invalid": 1, "notfound": 1}


def test_unparseable_prefix_left_null(conn):
    conn.execute("INSERT INTO riswhois (origin_as, prefix, type) VALUES ('1', 'bogus', 'badipv4')")
    rov.run(conn, rov.load_index(conn))
    row = conn.execute("SELECT rovstatus, rovreason, rov_roas FROM riswhois").fetchone()
    assert row == (None, None, None)


def test_batches_and_progress(conn, monkeypatch):
    monkeypatch.setattr(rov, "BATCH", 2)
    ticks = []
    for i in range(5):
        conn.execute(
            "INSERT INTO riswhois (origin_as, prefix, type, istart, pfxlen) VALUES (?,?,?,?,?)",
            ("28000", f"200.40.{i}.0/24", "ipv4", from_prefix(f"200.40.{i}.0/24").istart, 24),
        )
    stats = rov.run(conn, rov.load_index(conn), ticks.append)
    assert ticks == [2, 2, 1]
    assert stats == {"valid": 5}


def test_empty_tables():
    c = sqlite3.connect(":memory:")
    db.create_table(c, "roadata")
    db.create_table(c, "riswhois")
    assert rov.run(c, rov.load_index(c)) == {}
