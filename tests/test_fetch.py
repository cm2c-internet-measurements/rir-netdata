import gzip
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


class _Bar:
    """Records what ``fetch`` tells its progress display."""

    def __init__(self):
        self.total = self.completed = None

    def add_task(self, description, total):
        return 1

    def update(self, task, total=None, completed=None):
        self.total = total if total is not None else self.total
        self.completed = completed if completed is not None else self.completed

    def advance(self, task, n):
        self.completed = (self.completed or 0) + n

    def remove_task(self, task):
        pass


def test_compressed_transfer_is_stored_decoded(tmp_path):
    body = BODY * 5000
    wire = gzip.compress(body)
    seen = []

    def handler(request):
        seen.append(request.headers["accept-encoding"])
        headers = {"content-encoding": "gzip", "content-length": str(len(wire))}
        return httpx.Response(200, stream=httpx.ByteStream(wire), headers=headers)  # streamed

    bar = _Bar()
    client = make_client(httpx.MockTransport(handler))
    got = fetch(client, URL, tmp_path / "f", max_age=3600, retry_cfg=NO_WAIT, progress=bar)
    assert "gzip" in seen[0]
    assert got.path.read_bytes() == body
    assert got.sha256 == hashlib.sha256(body).hexdigest()  # of the content, not the transfer
    assert bar.total == bar.completed == len(wire) < len(body)  # progress counts wire bytes


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
