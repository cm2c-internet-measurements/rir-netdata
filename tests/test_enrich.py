import sqlite3

import pytest

from rir_netdata import db, enrich
from rir_netdata.addr import from_delegated, from_prefix
from rir_netdata.sources.rpki import origin_as2

NUMRES = [
    # rir, cc, type, block, length, status
    ("lacnic", "UY", "ipv4", "200.40.0.0", 65536, "allocated"),
    ("lacnic", "", "ipv4", "200.41.0.0", 256, "available"),
    ("lacnic", "BR", "ipv4", "200.42.0.0", 256, "assigned"),
    ("ripencc", "NL", "ipv4", "193.0.0.0", 4096, "allocated"),
    ("lacnic", "AR", "ipv6", "2800::", 32, "allocated"),
    ("lacnic", "UY", "asn", "28000", 1, "assigned"),
    ("lacnic", "CL", "asn", "27000", 10, "allocated"),
    ("lacnic", "", "asn", "64000", 10, "reserved"),
]


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    db.create_table(c, "numres")
    db.create_table(c, "roadata")
    for rir, cc, rtype, block, length, status in NUMRES:
        r = from_delegated(rtype, block, length)
        c.execute(
            "INSERT INTO numres (rir, cc, type, block, length, status, istart, iend, prefix, equiv)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rir, cc, rtype, block, length, status, r.istart, r.iend, r.prefix, r.equiv),
        )
    db.create_indexes(c, "numres")
    yield c
    c.close()


def _roa(conn, origin, prefix, ta="lacnic"):
    r = from_prefix(prefix)
    conn.execute(
        "INSERT INTO roadata (origin_as, prefix, ta, origin_as2, istart, iend, type, pfxlen)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (origin, prefix, ta, origin_as2(origin), r.istart, r.iend, r.type, r.pfxlen),
    )


def _ccs(conn, prefix):
    return conn.execute(
        "SELECT cc, origin_as_cc FROM roadata WHERE prefix = ?", (prefix,)
    ).fetchone()


def test_match_prefix_and_origin(conn):
    _roa(conn, "AS28000", "200.40.128.0/17")
    assert enrich.run(conn) == 1
    assert _ccs(conn, "200.40.128.0/17") == ("UY", "UY")


def test_asn_inside_a_block(conn):
    _roa(conn, "AS27009", "200.42.0.0/24")
    enrich.run(conn)
    assert _ccs(conn, "200.42.0.0/24") == ("BR", "CL")


def test_no_match_is_zz(conn):
    _roa(conn, "AS65000", "8.8.8.0/24")
    enrich.run(conn)
    assert _ccs(conn, "8.8.8.0/24") == ("ZZ", "ZZ")


def test_just_past_the_end_of_a_block_is_zz(conn):
    _roa(conn, "AS27010", "200.40.255.255/32")
    enrich.run(conn)
    assert _ccs(conn, "200.40.255.255/32") == ("UY", "ZZ")


def test_available_and_reserved_space_is_zz(conn):
    _roa(conn, "AS64001", "200.41.0.0/24")
    enrich.run(conn)
    assert _ccs(conn, "200.41.0.0/24") == ("ZZ", "ZZ")


def test_family_is_checked(conn):
    # IPv4 addresses and ASNs share the integer space 0..2**32: 0.0.109.96 is 28000, which is
    # AS28000's number. Without the type check this ROA would get cc 'UY' from the ASN row.
    _roa(conn, "AS65000", "0.0.109.96/32")
    enrich.run(conn)
    assert _ccs(conn, "0.0.109.96/32") == ("ZZ", "ZZ")


def test_ipv6_outside_global_unicast_is_zz(conn):
    _roa(conn, "AS28000", "fc00::/7")
    enrich.run(conn)
    assert _ccs(conn, "fc00::/7") == ("ZZ", "UY")


def test_ipv6_match(conn):
    _roa(conn, "AS28000", "2800:0:1::/48")
    enrich.run(conn)
    assert _ccs(conn, "2800:0:1::/48") == ("AR", "UY")


def test_all_trust_anchors_enriched(conn):
    _roa(conn, "AS28000", "193.0.0.0/21", ta="ripe")
    _roa(conn, "AS28000", "200.40.0.0/16", ta="arin")
    enrich.run(conn)
    assert _ccs(conn, "193.0.0.0/21") == ("NL", "UY")
    assert _ccs(conn, "200.40.0.0/16") == ("UY", "UY")


def test_bad_prefix_is_zz(conn):
    _roa(conn, "AS28000", "IP Prefix")
    enrich.run(conn)
    assert _ccs(conn, "IP Prefix") == ("ZZ", "UY")


def test_batches_and_progress(conn, monkeypatch):
    monkeypatch.setattr(enrich, "BATCH", 2)
    for i in range(5):
        _roa(conn, "AS28000", f"200.40.{i}.0/24")
    ticks = []
    assert enrich.run(conn, ticks.append) == 5
    assert ticks == [2, 2, 1]
    assert conn.execute("SELECT count(*) FROM roadata WHERE cc = 'UY'").fetchone()[0] == 5


def test_empty_roadata(conn):
    assert enrich.run(conn) == 0


def test_lookup_uses_range_index(conn):
    plan = conn.execute("EXPLAIN QUERY PLAN " + enrich._UPDATE, (1, 1)).fetchall()
    details = " ".join(row[-1] for row in plan)
    assert "numres_type_range" in details
