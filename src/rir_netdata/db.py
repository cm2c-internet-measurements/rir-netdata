"""Output database: schema (SPEC.md §5), atomic build, provenance rows."""

import os
import sqlite3
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import astuple, dataclass, fields
from pathlib import Path

# Verbatim from SPEC.md §5; tests/test_db.py checks they stay in sync.
DDL = {
    "numres": (
        "CREATE TABLE numres (id INTEGER PRIMARY KEY, rir text, cc text, type text, block text,"
        " length integer, date integer, status text, orgid integer, istart INTEGER, iend INTEGER,"
        " prefix VARCHAR(80), equiv INTEGER);"
    ),
    "roadata": (
        "CREATE TABLE roadata (id INTEGER PRIMARY KEY, origin_as text, prefix text, maxlen integer,"
        " ta text, origin_as2 VARCHAR(10), istart UNSIGNED BIG INT, iend UNSIGNED BIG INT,"
        " type VARCHAR(5), pfxlen INTEGER, equiv INTEGER, cc CHAR(2), origin_as_cc CHAR(2),"
        " equiv2 INTEGER);"
    ),
    "aspadata": (
        "CREATE TABLE aspadata (id INTEGER PRIMARY KEY, asid integer, providers text, ta text,"
        " asid_cc CHAR(2));"
    ),
    "aspa_providers": "CREATE TABLE aspa_providers (asid integer, provider integer, ta text);",
    "riswhois": (
        "CREATE TABLE riswhois (id INTEGER PRIMARY KEY, origin_as text, prefix text,"
        " viewed_by integer, istart UNSIGNED BIG INT, iend UNSIGNED BIG INT, type VARCHAR(5),"
        " pfxlen INTEGER, rovstatus text, rovreason text, rov_roas integer);"
    ),
    "meta": (
        "CREATE TABLE meta (source text, url text, fetched_at_utc text, source_serial text,"
        " row_count integer, sha256 text, tool_version text, run_started_at_utc text);"
    ),
}

# Created after the bulk load, which is much faster than maintaining them during inserts.
INDEXES = {
    "numres": ["CREATE INDEX numres_type_range ON numres (type, istart, iend);"],
    "aspa_providers": ["CREATE INDEX aspa_providers_provider ON aspa_providers (provider);"],
}


@dataclass(frozen=True, slots=True)
class MetaRow:
    source: str
    url: str
    fetched_at_utc: str
    source_serial: str | None
    row_count: int
    sha256: str
    tool_version: str
    run_started_at_utc: str


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


@contextmanager
def build(target: Path) -> Iterator[sqlite3.Connection]:
    """Yield a connection to a temp db next to ``target``; rename it into place only on success."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    conn = sqlite3.connect(tmp)
    # The temp file is discarded on any failure, so journaling and per-commit syncs protect
    # nothing; skipping them matters on slow filesystems (e.g. container bind mounts on macOS).
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA synchronous = OFF")
    try:
        conn.execute(DDL["meta"])
        yield conn
        conn.commit()
        conn.close()
        with tmp.open("rb+") as fh:  # one sync before the rename makes the published file durable
            os.fsync(fh.fileno())
        tmp.chmod(0o666 & ~_umask())  # mkstemp creates 0600; the db is meant to be shared
        tmp.replace(target)
    except BaseException:
        conn.close()
        tmp.unlink(missing_ok=True)
        raise


def create_table(conn: sqlite3.Connection, table: str) -> None:
    conn.execute(DDL[table])


def create_indexes(conn: sqlite3.Connection, table: str) -> None:
    for sql in INDEXES.get(table, []):
        conn.execute(sql)


def write_meta(conn: sqlite3.Connection, rows: Iterable[MetaRow]) -> None:
    cols = [f.name for f in fields(MetaRow)]
    sql = f"INSERT INTO meta ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    conn.executemany(sql, (astuple(r) for r in rows))
