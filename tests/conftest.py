"""Shared fixtures: a mock HTTP server for every default source URL, and CLI helpers."""

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


def run_get(*args: str):
    return runner.invoke(app, ["get", "--config", "netdata.toml", "--output-dir", "out", *args])


def built_db(tmp_path: Path) -> Path:
    (db,) = (tmp_path / "out").glob("netdata-*.db")
    return db
