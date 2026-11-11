import sqlite3

import pytest

from rir_netdata import db, enrich
from rir_netdata.addr import from_delegated
from rir_netdata.sources import aspa
from rir_netdata.sources.rpki import FormatError


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    for t in ("numres", "aspadata", "aspa_providers"):
        db.create_table(c, t)
    yield c
    c.close()


@pytest.mark.parametrize(
    ("given", "want"), [("AS43", 43), ("as0", 0), ("AS4200000000", 4200000000)]
)
def test_asn(given, want):
    assert aspa.asn(given) == want


@pytest.mark.parametrize("bad", ["43", "AS", "AS4x", "{AS1}", 43, None])
def test_asn_rejects_anything_else(bad):
    with pytest.raises(FormatError, match="unexpected AS number"):
        aspa.asn(bad)


@pytest.mark.parametrize("bad", [{"customer": "AS1", "ta": "ripe"}, "AS1", {"providers": []}])
def test_malformed_entries_fail(bad):
    with pytest.raises(FormatError, match="malformed"):
        list(aspa.parse([bad]))


def test_load_both_tables(conn):
    aspas = [
        {"customer": "AS64500", "providers": ["AS65002", "AS174", "AS65001"], "ta": "ripe"},
        {"customer": "AS64501", "providers": ["AS0"], "ta": "lacnic"},
    ]
    assert aspa.load(conn, aspas) == 2
    assert conn.execute("SELECT asid, providers, ta, asid_cc FROM aspadata").fetchall() == [
        (64500, "174,65001,65002", "ripe", None),  # sorted numerically, not as strings
        (64501, "0", "lacnic", None),
    ]
    assert conn.execute("SELECT * FROM aspa_providers ORDER BY rowid").fetchall() == [
        (64500, 174, "ripe"),
        (64500, 65001, "ripe"),
        (64500, 65002, "ripe"),
        (64501, 0, "lacnic"),
    ]
    types = conn.execute("SELECT DISTINCT typeof(asid), typeof(provider) FROM aspa_providers")
    assert types.fetchall() == [("integer", "integer")]


def test_load_nothing(conn):
    assert aspa.load(conn, []) == 0
    assert conn.execute("SELECT count(*) FROM aspa_providers").fetchone()[0] == 0


def test_enrich_asid_cc(conn):
    for cc, block, length, status in [
        ("UY", "28000", 1, "assigned"),
        ("CL", "27000", 10, "allocated"),
        ("", "64000", 10, "reserved"),
    ]:
        r = from_delegated("asn", block, length)
        conn.execute(
            "INSERT INTO numres (rir, cc, type, block, length, status, istart, iend)"
            " VALUES ('lacnic', ?, 'asn', ?, ?, ?, ?, ?)",
            (cc, block, length, status, r.istart, r.iend),
        )
    db.create_indexes(conn, "numres")
    aspas = [
        {"customer": f"AS{n}", "providers": ["AS174"], "ta": "lacnic"}
        for n in (28000, 27009, 27010, 64005, 1)
    ]
    aspa.load(conn, aspas)
    assert enrich.run_aspa(conn) == 5
    got = conn.execute("SELECT asid, asid_cc FROM aspadata ORDER BY id").fetchall()
    assert got == [
        (28000, "UY"),
        (27009, "CL"),  # inside a 10-ASN block
        (27010, "ZZ"),  # just past its end
        (64005, "ZZ"),  # reserved, not allocated/assigned
        (1, "ZZ"),
    ]
