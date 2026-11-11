import json
import sqlite3

from conftest import FIXTURES
from conftest import built_db as _db
from conftest import run_get as _get

from rir_netdata import config


def test_delegated_run_builds_db(serve, tmp_path):
    result = _get("--source", "delegated")
    assert result.exit_code == 0, result.output
    with sqlite3.connect(_db(tmp_path)) as conn:
        meta = conn.execute("SELECT source, row_count, source_serial, tool_version FROM meta")
        meta = {m[0]: m[1:] for m in meta}
        assert set(meta) == {f"delegated-{r}" for r in config.RIRS}
        assert meta["delegated-lacnic"][:2] == (22, "20261110")
        total = conn.execute("SELECT count(*) FROM numres").fetchone()[0]
        assert total == sum(m[0] for m in meta.values())
        indexes = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        assert ("numres_type_range",) in indexes


def test_single_rir(serve, tmp_path):
    assert _get("--source", "delegated", "--rir", "arin").exit_code == 0
    with sqlite3.connect(_db(tmp_path)) as conn:
        assert conn.execute("SELECT DISTINCT rir FROM numres").fetchall() == [("arin",)]


def test_failed_source_writes_nothing(serve, tmp_path):
    serve.add(config.DEFAULT_DELEGATED["apnic"])
    result = _get("--source", "delegated")
    assert result.exit_code == 1
    assert "no database written" in result.output
    assert not list((tmp_path / "out").glob("*"))


def test_bad_config_exit_code(serve, tmp_path):
    (tmp_path / "netdata.toml").write_text("bogus = 1\n")
    assert _get().exit_code == 2


def test_full_run_builds_all_tables(serve, tmp_path):
    result = _get()
    assert result.exit_code == 0, result.output
    with sqlite3.connect(_db(tmp_path)) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"meta", "numres", "roadata", "aspadata", "aspa_providers", "riswhois"}
        meta = dict(conn.execute("SELECT source, row_count FROM meta").fetchall())
        assert meta["rpki-roas"] == 12
        assert meta["rpki-aspas"] == 4
        assert meta["riswhois-ipv4"] == 5
        assert conn.execute("SELECT count(*) FROM riswhois").fetchone()[0] == (
            meta["riswhois-ipv4"] + meta["riswhois-ipv6"]
        )


def test_rpki_meta_has_routinator_generation_time(serve, tmp_path):
    assert _get("--source", "rpki").exit_code == 0
    with sqlite3.connect(_db(tmp_path)) as conn:
        rows = conn.execute("SELECT source, url, source_serial FROM meta").fetchall()
    url = config.DEFAULT_RPKI["url"]
    assert rows == [
        ("rpki-roas", url, "2026-11-10T15:20:32Z"),
        ("rpki-aspas", url, "2026-11-10T15:20:32Z"),
    ]


def test_rpki_csv_instead_of_json_fails_clearly(serve, tmp_path):
    url = "https://rpki.example.net/csv"
    (tmp_path / "netdata.toml").write_text(
        (tmp_path / "netdata.toml").read_text() + f'[sources.rpki]\nurl = "{url}"\n'
    )
    serve.routes[url] = b"ASN,IP Prefix,Max Length,Trust Anchor\nAS1,1.0.0.0/24,24,apnic\n"
    result = _get("--source", "rpki")
    assert result.exit_code == 1
    assert "Routinator JSON" in result.output
    assert not list((tmp_path / "out").glob("*"))


def test_rpki_failure_writes_nothing(serve, tmp_path):
    serve.add(config.DEFAULT_RPKI["url"])
    assert _get().exit_code == 1
    assert not list((tmp_path / "out").glob("*"))


def test_full_run_enriches_roadata(serve, tmp_path):
    assert _get().exit_code == 0
    with sqlite3.connect(_db(tmp_path)) as conn:
        assert conn.execute("SELECT count(*) FROM roadata WHERE cc IS NULL").fetchone()[0] == 0
        cc = conn.execute("SELECT cc FROM roadata WHERE prefix = '2.152.0.0/22'").fetchone()[0]
        assert cc == "GT"  # lacnic|GT|ipv4|2.152.0.0|1024|...|allocated in the fixture


def test_full_run_loads_and_enriches_aspas(serve, tmp_path):
    result = _get()
    assert result.exit_code == 0, result.output
    assert "load rpki → roadata, aspadata, aspa_providers" in result.output
    assert "enrich aspadata asid_cc" in result.output
    with sqlite3.connect(_db(tmp_path)) as conn:
        rows = conn.execute("SELECT asid, providers, ta, asid_cc FROM aspadata ORDER BY id")
        assert rows.fetchall() == [
            (278, "174,3356", "lacnic", "MX"),  # lacnic|MX|asn|278 in the fixture
            (1228, "0", "afrinic", "ZA"),  # AS0: declares no providers
            (676, "174,6939", "lacnic", "AR"),  # sorted
            (4200000001, "1299", "ripe", "ZZ"),  # in no delegated file
        ]
        pairs = conn.execute("SELECT asid FROM aspa_providers WHERE provider = 174 ORDER BY 1")
        assert pairs.fetchall() == [(278,), (676,)]
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "aspa_providers_provider" in indexes


def test_rpki_only_run_skips_enrichment(serve, tmp_path):
    result = _get("--source", "rpki")
    assert result.exit_code == 0, result.output
    assert "left NULL" in result.output and "asid_cc" in result.output
    with sqlite3.connect(_db(tmp_path)) as conn:
        assert conn.execute("SELECT count(*) FROM roadata WHERE cc IS NOT NULL").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM aspadata").fetchone()[0] == 4
        filled = conn.execute("SELECT count(*) FROM aspadata WHERE asid_cc IS NOT NULL")
        assert filled.fetchone()[0] == 0


def test_export_without_aspas_warns(serve, tmp_path):
    body = json.loads((FIXTURES / "rpki.json").read_text())
    del body["aspas"]
    serve.routes[config.DEFAULT_RPKI["url"]] = json.dumps(body).encode()
    result = _get("--source", "rpki")
    assert result.exit_code == 0, result.output
    assert "no ASPAs" in result.output
    with sqlite3.connect(_db(tmp_path)) as conn:
        meta = dict(conn.execute("SELECT source, row_count FROM meta").fetchall())
    assert meta == {"rpki-roas": 12, "rpki-aspas": 0}


def test_full_run_validates_riswhois(serve, tmp_path):
    result = _get()
    assert result.exit_code == 0, result.output
    assert "ROV" in result.output
    with sqlite3.connect(_db(tmp_path)) as conn:
        nulls = conn.execute("SELECT count(*) FROM riswhois WHERE rovstatus IS NULL").fetchone()[0]
        assert nulls == 0
        statuses = {r[0] for r in conn.execute("SELECT DISTINCT rovstatus FROM riswhois")}
        assert statuses <= {"valid", "invalid", "notfound"}


def test_riswhois_only_run_skips_rov(serve, tmp_path):
    result = _get("--source", "riswhois")
    assert result.exit_code == 0, result.output
    assert "rovstatus" in result.output and "left NULL" in result.output
    with sqlite3.connect(_db(tmp_path)) as conn:
        filled = conn.execute("SELECT count(*) FROM riswhois WHERE rovstatus IS NOT NULL")
        assert filled.fetchone()[0] == 0
