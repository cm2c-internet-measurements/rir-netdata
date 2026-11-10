import sqlite3
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from rir_netdata import config, fetch, pipeline
from rir_netdata.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def _routes(cfg: config.Config) -> dict[str, Path]:
    routes = {cfg.delegated[r]: FIXTURES / f"delegated-{r}.txt" for r in config.RIRS}
    routes[cfg.rpki["url"]] = FIXTURES / "rpki.csv.txt"
    routes[cfg.riswhois["ipv4"]] = FIXTURES / "riswhoisdump.IPv4.gz"
    routes[cfg.riswhois["ipv6"]] = FIXTURES / "riswhoisdump.IPv6.gz"
    return routes


@pytest.fixture
def serve(monkeypatch, tmp_path):
    """Serve fixtures for every default URL; return the set of URLs to answer with 404."""
    failing: set[str] = set()
    routes = _routes(config.Config())

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in failing or url not in routes:
            return httpx.Response(404)
        return httpx.Response(200, content=routes[url].read_bytes())

    monkeypatch.setattr(
        pipeline, "make_client", lambda: fetch.make_client(httpx.MockTransport(handler))
    )
    cfg_file = tmp_path / "netdata.toml"
    cfg_file.write_text(f'cache_dir = "{tmp_path / "cache"}"\n[retry]\nmax_wait_seconds = 0\n')
    monkeypatch.chdir(tmp_path)
    return failing


def _get(*args: str):
    return runner.invoke(app, ["get", "--config", "netdata.toml", "--output-dir", "out", *args])


def _db(tmp_path: Path) -> Path:
    (db,) = (tmp_path / "out").glob("netdata-*.db")
    return db


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
        assert tables == {"meta", "numres", "roadata", "riswhois"}
        meta = dict(conn.execute("SELECT source, row_count FROM meta").fetchall())
        assert meta["rpki"] == 12
        assert meta["riswhois-ipv4"] == 5
        assert conn.execute("SELECT count(*) FROM riswhois").fetchone()[0] == (
            meta["riswhois-ipv4"] + meta["riswhois-ipv6"]
        )


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


def test_rpki_only_run_skips_enrichment(serve, tmp_path):
    result = _get("--source", "rpki")
    assert result.exit_code == 0, result.output
    assert "left NULL" in result.output
    with sqlite3.connect(_db(tmp_path)) as conn:
        assert conn.execute("SELECT count(*) FROM roadata WHERE cc IS NOT NULL").fetchone()[0] == 0


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
