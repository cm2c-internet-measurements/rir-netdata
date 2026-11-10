"""RIR delegated-extended files → ``numres`` (SPEC.md §4.1)."""

import csv
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import petl

from rir_netdata.addr import from_delegated

SRC_COLS = ("rir", "cc", "type", "block", "length", "date", "status", "orgid")
OUT_COLS = (*SRC_COLS, "istart", "iend", "prefix", "equiv")
ENCODING = {"encoding": "utf-8", "errors": "replace"}


class ReconcileError(ValueError):
    """Loaded record counts don't match the file's own summary lines (e.g. truncated download)."""


@dataclass(frozen=True)
class Preamble:
    registry: str
    serial: str
    summary: dict[str, int] = field(default_factory=dict)


def _is_comment(row: list[str]) -> bool:
    return not row or not row[0] or row[0].startswith("#")


def _is_version(row) -> bool:
    return row[0][:1].isdigit()


def _is_summary(row) -> bool:
    return len(row) > 5 and row[5] == "summary"


def _is_record(row) -> bool:
    return not (_is_comment(row) or _is_version(row) or _is_summary(row))


def read_preamble(path: Path) -> Preamble:
    """Parse the version header and summary lines that precede the records."""
    header, summary = None, {}
    with path.open(newline="", **ENCODING) as fh:
        for row in csv.reader(fh, delimiter="|"):
            if _is_comment(row):
                continue
            if _is_version(row):
                header = row
            elif _is_summary(row):
                summary[row[2]] = int(row[4])
            else:
                break
    if header is None:
        raise ValueError(f"{path}: no version header line")
    return Preamble(registry=header[1], serial=header[2], summary=summary)


def _derive(row) -> tuple:
    res = from_delegated(row.type, row.block, int(row.length))
    return (*row, res.istart, res.iend, res.prefix, res.equiv)


def table(path: Path) -> petl.Table:
    """Lazy petl table of ``numres`` rows: records only, extensions dropped, columns derived."""
    return petl.rowmap(
        petl.fromcsv(str(path), delimiter="|", header=list(SRC_COLS), **ENCODING)
        .select(_is_record)
        .cut(*SRC_COLS),
        _derive,
        header=list(OUT_COLS),
    )


def load(conn: sqlite3.Connection, path: Path) -> tuple[Preamble, int]:
    """Append one RIR's file to ``numres``; return its preamble and the number of rows loaded."""
    pre = read_preamble(path)
    petl.appenddb(table(path), conn, "numres", commit=False)
    counts = dict(
        conn.execute(
            "SELECT type, count(*) FROM numres WHERE rir = ? GROUP BY type", (pre.registry,)
        ).fetchall()
    )
    if pre.summary and counts != pre.summary:
        raise ReconcileError(f"{pre.registry}: loaded {counts}, file summary says {pre.summary}")
    return pre, sum(counts.values())
