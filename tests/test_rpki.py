import json
import sqlite3
from pathlib import Path

import pytest

from rir_netdata import db
from rir_netdata.sources import rpki

FIXTURE = Path(__file__).parent / "fixtures" / "rpki.json"


def _load(conn) -> int:
    return rpki.load_roas(conn, rpki.read(FIXTURE)["roas"])


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


def test_every_roa_loaded_in_order(conn):
    roas = json.loads(FIXTURE.read_text())["roas"]
    assert _load(conn) == len(roas) == 12
    got = conn.execute("SELECT origin_as, prefix, maxlen, ta FROM roadata ORDER BY id").fetchall()
    assert [tuple(r) for r in got] == [
        (r["asn"], r["prefix"], r["maxLength"], r["ta"]) for r in roas
    ]
    assert conn.execute("SELECT count(*) FROM roadata WHERE type LIKE 'bad%'").fetchone()[0] == 0


def test_serial_is_generation_time():
    assert rpki.serial(rpki.read(FIXTURE)) == "2026-11-10T15:20:32Z"
    assert rpki.serial({"roas": []}) is None


@pytest.mark.parametrize(
    "content",
    [
        b"ASN,IP Prefix,Max Length,Trust Anchor\nAS1,1.0.0.0/24,24,apnic\n",  # the old CSV
        b'{"metadata": {}}',
        b"[]",
        b"\xff\xfe",
    ],
)
def test_anything_but_routinator_json_fails_clearly(tmp_path, content):
    path = tmp_path / "rpki-routinator.json"
    path.write_bytes(content)
    with pytest.raises(rpki.FormatError, match="Routinator JSON"):
        rpki.read(path)


def test_ipv4_roa(conn):
    _load(conn)
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
        "equiv2": 4,
    }


def test_ipv6_roa(conn):
    _load(conn)
    r = conn.execute("SELECT * FROM roadata WHERE origin_as = 'AS22894'").fetchone()
    assert (r["type"], r["pfxlen"], r["equiv"], r["equiv2"]) == (
        "ipv6",
        48,
        1.52587890625e-05,
        65536,
    )
    assert r["istart"] == 0x2001120100000000
    assert r["iend"] == 0x200112010000FFFF


def test_every_trust_anchor_kept(conn):
    _load(conn)
    tas = {r[0] for r in conn.execute("SELECT DISTINCT ta FROM roadata")}
    assert tas == {"afrinic", "apnic", "arin", "lacnic", "ripe"}
