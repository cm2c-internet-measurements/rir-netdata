import hashlib
import os
import time

import httpx
import pytest

from rir_netdata.config import Retry
from rir_netdata.fetch import fetch, make_client

URL = "https://example.net/data"
BODY = b"lacnic|AR|ipv4|200.0.0.0|256|20000101|allocated|1\n"
NO_WAIT = Retry(attempts=3, max_wait_seconds=0)


def _client(responses):
    """Client whose transport replays ``responses`` (status codes or exceptions) in order."""
    calls = []

    def handler(request):
        calls.append(request)
        r = responses[min(len(calls), len(responses)) - 1]
        if isinstance(r, Exception):
            raise r
        return httpx.Response(r, content=BODY if r == 200 else b"")

    return make_client(httpx.MockTransport(handler)), calls


def test_downloads_and_hashes(tmp_path):
    client, calls = _client([200])
    got = fetch(client, URL, tmp_path / "f", max_age=3600, retry_cfg=NO_WAIT)
    assert got.path.read_bytes() == BODY
    assert got.sha256 == hashlib.sha256(BODY).hexdigest()
    assert not got.from_cache
    assert len(calls) == 1
    assert calls[0].headers["user-agent"].startswith("rir-netdata/")


def test_retries_transient_errors(tmp_path):
    client, calls = _client([503, httpx.ConnectError("boom"), 200])
    got = fetch(client, URL, tmp_path / "f", max_age=3600, retry_cfg=NO_WAIT)
    assert got.path.read_bytes() == BODY
    assert len(calls) == 3


def test_gives_up_after_attempts(tmp_path):
    client, calls = _client([503])
    with pytest.raises(httpx.HTTPStatusError):
        fetch(client, URL, tmp_path / "f", max_age=3600, retry_cfg=NO_WAIT)
    assert len(calls) == 3
    assert list(tmp_path.iterdir()) == []


def test_does_not_retry_404(tmp_path):
    client, calls = _client([404])
    with pytest.raises(httpx.HTTPStatusError):
        fetch(client, URL, tmp_path / "f", max_age=3600, retry_cfg=NO_WAIT)
    assert len(calls) == 1


def test_fresh_cache_is_reused(tmp_path):
    dest = tmp_path / "f"
    dest.write_bytes(b"cached")
    client, calls = _client([200])
    got = fetch(client, URL, dest, max_age=3600, retry_cfg=NO_WAIT)
    assert got.from_cache
    assert dest.read_bytes() == b"cached"
    assert calls == []


def test_stale_cache_is_refreshed(tmp_path):
    dest = tmp_path / "f"
    dest.write_bytes(b"cached")
    old = time.time() - 7200
    os.utime(dest, (old, old))
    client, calls = _client([200])
    got = fetch(client, URL, dest, max_age=3600, retry_cfg=NO_WAIT)
    assert not got.from_cache
    assert dest.read_bytes() == BODY
    assert len(calls) == 1


def test_failed_refresh_keeps_old_copy(tmp_path):
    dest = tmp_path / "f"
    dest.write_bytes(b"cached")
    os.utime(dest, (0, 0))
    client, _ = _client([httpx.ReadTimeout("slow")])
    with pytest.raises(httpx.ReadTimeout):
        fetch(client, URL, dest, max_age=3600, retry_cfg=NO_WAIT)
    assert dest.read_bytes() == b"cached"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["f"]


@pytest.mark.network
def test_live_sources_reachable(tmp_path):
    from rir_netdata.config import load

    cfg = load()
    urls = [*cfg.delegated.values(), *cfg.riswhois.values()]
    with make_client() as client:
        for url in urls:
            assert client.head(url).status_code == 200, url
