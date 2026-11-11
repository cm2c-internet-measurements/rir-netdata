"""Cached HTTP downloads with retries."""

import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from rich.progress import Progress
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from rir_netdata import __version__
from rir_netdata.config import Retry

# No total deadline: Routinator streams its export slowly but steadily.
TIMEOUT = httpx.Timeout(30.0, read=120.0)
CHUNK = 1 << 16


@dataclass(frozen=True, slots=True)
class Fetched:
    path: Path
    url: str
    fetched_at_utc: str
    sha256: str
    from_cache: bool


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


@retry(
    retry=retry_if_exception(_is_transient),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, max=60),
    reraise=True,
)
def _download(client: httpx.Client, url: str, dest: Path, progress: Progress | None) -> None:
    """Stream ``url`` into ``dest``.

    httpx asks for compressed transfer (``Accept-Encoding: gzip, deflate``) and decodes it, so
    ``dest`` (and its sha256) is always the uncompressed content. Progress counts bytes on the
    wire, which is what ``Content-Length`` measures.
    """
    part = dest.with_name(dest.name + ".part")
    task = progress.add_task(dest.name, total=None) if progress else None
    try:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            if progress and task is not None and "content-length" in resp.headers:
                progress.update(task, total=int(resp.headers["content-length"]))
            with part.open("wb") as fh:
                for chunk in resp.iter_bytes(CHUNK):
                    fh.write(chunk)
                    if progress and task is not None:
                        progress.update(task, completed=resp.num_bytes_downloaded)
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)
        if progress and task is not None:
            progress.remove_task(task)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": f"rir-netdata/{__version__}"},
        transport=transport,
    )


def fetch(
    client: httpx.Client,
    url: str,
    dest: Path,
    *,
    max_age: float,
    retry_cfg: Retry,
    progress: Progress | None = None,
) -> Fetched:
    """Download ``url`` to ``dest`` unless a copy younger than ``max_age`` seconds exists."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    from_cache = dest.exists() and time.time() - dest.stat().st_mtime < max_age
    if not from_cache:
        _download.retry_with(
            stop=stop_after_attempt(retry_cfg.attempts),
            wait=wait_exponential(multiplier=1, max=retry_cfg.max_wait_seconds),
        )(client, url, dest, progress)
    return Fetched(dest, url, _iso_utc(dest.stat().st_mtime), _sha256(dest), from_cache)
