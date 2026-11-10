import sqlite3
from pathlib import Path

import pytest

from rir_netdata import db
from rir_netdata.config import RIRS
from rir_netdata.sources import delegated

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(rir: str) -> Path:
    return FIXTURES / f"delegated-{rir}.txt"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    db.create_table(c, "numres")
    yield c
    c.close()


def _rows(conn, where="1=1", params=()):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(f"SELECT * FROM numres WHERE {where}", params)]


def test_preamble():
    pre = delegated.read_preamble(_fixture("lacnic"))
    assert pre.registry == "lacnic"
    assert pre.serial == "20261110"
    assert pre.summary == {"asn": 7, "ipv4": 7, "ipv6": 8}


def test_preamble_skips_leading_comments():
    assert delegated.read_preamble(_fixture("apnic")).registry == "apnic"


@pytest.mark.parametrize("rir", RIRS)
def test_every_rir_loads_and_reconciles(conn, rir):
    pre, n = delegated.load(conn, _fixture(rir))
    assert n == sum(pre.summary.values())
    rows = _rows(conn)
    assert {r["rir"] for r in rows} == {rir}
    assert not [r for r in rows if r["block"] == "*" or r["status"] == "summary"]
    assert not [r for r in rows if r["rir"][:1].isdigit() or r["rir"].startswith("#")]


def test_all_rirs_into_one_table(conn):
    for rir in RIRS:
        delegated.load(conn, _fixture(rir))
    assert {r[0] for r in conn.execute("SELECT DISTINCT rir FROM numres")} == set(RIRS)


def test_ipv4_record(conn):
    delegated.load(conn, _fixture("lacnic"))
    (r,) = _rows(conn, "block = ?", ("2.152.0.0",))
    assert r == {
        "id": r["id"],
        "rir": "lacnic",
        "cc": "GT",
        "type": "ipv4",
        "block": "2.152.0.0",
        "length": 1024,
        "date": 20260714,
        "status": "allocated",
        "orgid": 71316,
        "istart": 43515904,
        "iend": 43516927,
        "prefix": "2.152.0.0/22",
        "equiv": 4,
    }


def test_non_cidr_ipv4_gets_range_prefix(conn):
    delegated.load(conn, _fixture("arin"))
    (r,) = _rows(conn, "block = ?", ("23.128.1.0",))
    assert r["prefix"] == "23.128.1.0-23.128.3.255"
    assert r["iend"] - r["istart"] + 1 == 768


def test_seven_field_row_has_null_orgid(conn):
    delegated.load(conn, _fixture("lacnic"))
    (r,) = _rows(conn, "block = ?", ("192.135.95.0",))
    assert (r["status"], r["cc"], r["orgid"]) == ("available", "", None)


def test_extension_fields_dropped(conn):
    delegated.load(conn, _fixture("lacnic"))
    (r,) = _rows(conn, "type = 'asn' AND block = '64512'")
    assert (r["orgid"], r["istart"], r["iend"], r["prefix"], r["equiv"]) == (
        99999,
        64512,
        64513,
        "na/asn",
        2,
    )


def test_ipv6_in_slash64_units(conn):
    delegated.load(conn, _fixture("lacnic"))
    (r,) = _rows(conn, "block = ?", ("2001:1200::",))
    assert (r["istart"], r["iend"], r["equiv"]) == (0x2001120000000000, 0x20011200FFFFFFFF, 1)


def test_truncated_file_fails_reconcile(conn, tmp_path):
    lines = _fixture("lacnic").read_text().splitlines()
    truncated = tmp_path / "delegated-lacnic.txt"
    truncated.write_text("\n".join(lines[:-3]) + "\n")
    with pytest.raises(delegated.ReconcileError):
        delegated.load(conn, truncated)


def test_missing_header_rejected(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("# just a comment\n")
    with pytest.raises(ValueError, match="no version header"):
        delegated.read_preamble(f)
