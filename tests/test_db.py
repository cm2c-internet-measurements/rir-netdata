import os
import re
import sqlite3
from pathlib import Path

import pytest

from rir_netdata import db

SPEC = Path(__file__).parents[1] / "SPEC.md"


def _norm(sql: str) -> str:
    return " ".join(sql.split())


def _spec_statements() -> dict[str, str]:
    """Map 'table' -> CREATE TABLE and 'table:idx' -> CREATE INDEX, as written in SPEC.md."""
    out = {}
    for block in re.findall(r"```sql\n(.*?)```", SPEC.read_text(), re.S):
        for stmt in filter(str.strip, block.split(";")):
            stmt = _norm(stmt) + ";"
            if m := re.match(r"CREATE TABLE (\w+)", stmt):
                out[m[1]] = stmt
            elif m := re.match(r"CREATE INDEX \w+ ON (\w+)", stmt):
                out[f"{m[1]}:idx"] = stmt
    return out


SPEC_SQL = _spec_statements()


@pytest.mark.parametrize("table", sorted(db.DDL))
def test_ddl_matches_spec(table):
    assert _norm(db.DDL[table]) == SPEC_SQL[table]


@pytest.mark.parametrize("table", sorted(db.INDEXES))
def test_indexes_match_spec(table):
    assert [_norm(s) for s in db.INDEXES[table]] == [SPEC_SQL[f"{table}:idx"]]


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}


def test_build_success_renames_into_place(tmp_path):
    target = tmp_path / "out" / "netdata-20261110.db"
    with db.build(target) as conn:
        db.create_table(conn, "numres")
        db.create_indexes(conn, "numres")
        db.write_meta(
            conn,
            [
                db.MetaRow(
                    "lacnic", "https://x", "2026-11-10T00:00:00Z", "20261109", 3, "ab", "2", "t"
                )
            ],
        )
    assert target.exists()
    assert _tables(target) == {"meta", "numres", "numres_type_range"}
    assert list(target.parent.iterdir()) == [target]
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT source, row_count FROM meta").fetchall() == [("lacnic", 3)]


def test_build_failure_leaves_nothing(tmp_path):
    target = tmp_path / "netdata.db"
    with pytest.raises(RuntimeError), db.build(target) as conn:
        db.create_table(conn, "numres")
        raise RuntimeError("source failed")
    assert list(tmp_path.iterdir()) == []


def test_build_failure_keeps_previous_file(tmp_path):
    target = tmp_path / "netdata.db"
    target.write_bytes(b"previous")
    with pytest.raises(RuntimeError), db.build(target):
        raise RuntimeError("source failed")
    assert target.read_bytes() == b"previous"


def test_output_respects_umask(tmp_path):
    old = os.umask(0o022)
    try:
        target = tmp_path / "netdata.db"
        with db.build(target):
            pass
    finally:
        os.umask(old)
    assert target.stat().st_mode & 0o777 == 0o644
