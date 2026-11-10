import csv
import re
import sqlite3
import tarfile
from pathlib import Path

import duckdb
import pytest
from conftest import built_db, run_get, runner

from rir_netdata import db, export, pipeline
from rir_netdata.cli import app


def _export_dir(tmp_path: Path) -> Path:
    (d,) = [p for p in (tmp_path / "out").iterdir() if p.is_dir()]
    return d


def _parquet_types(path: Path) -> dict[str, str]:
    with duckdb.connect() as con:
        rows = con.execute(
            f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM '{path}')"
        )
        return dict(rows.fetchall())


def _pq(sql: str):
    with duckdb.connect() as con:
        return con.execute(sql).fetchall()


class TestParseFormats:
    def test_comma_separated_and_repeated(self):
        got = export.parse_formats(["parquet,csv", "parquet"])
        assert got == [export.Format.parquet, export.Format.csv]

    def test_empty(self):
        assert export.parse_formats([]) == []
        assert export.parse_formats([" , "]) == []

    @pytest.mark.parametrize(("fmt", "issue"), [("jsonl", 12), ("duckdb", 13), ("sqlite.gz", 14)])
    def test_planned_formats_point_to_their_issue(self, fmt, issue):
        with pytest.raises(export.ExportError, match=f"#{issue}"):
            export.parse_formats([fmt])

    def test_unknown(self):
        with pytest.raises(export.ExportError, match="unknown export format 'xlsx'"):
            export.parse_formats(["xlsx"])


@pytest.fixture
def small_db(tmp_path):
    path = tmp_path / "netdata-20261110.db"
    conn = sqlite3.connect(path)
    for t in ("numres", "roadata", "meta"):
        db.create_table(conn, t)
    conn.executemany(
        "INSERT INTO numres (rir, cc, type, block, length, date, status, orgid, istart, iend,"
        " prefix, equiv) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                "lacnic",
                "UY",
                "ipv4",
                "200.40.0.0",
                65536,
                "20000101",
                "allocated",
                "71316",
                3358064640,
                3358130175,
                "200.40.0.0/16",
                256,
            ),
            ("arin", "", "ipv4", "23.128.1.0", 768, "", "reserved", "", 1, 768, "x-y", 3),
            ("arin", "US", "asn", "3", 1, "00000000", "assigned", 'd98c,"q"', 3, 3, "na/asn", 1),
        ],
    )
    conn.execute(
        "INSERT INTO roadata (origin_as, prefix, maxlen, ta, origin_as2, istart, iend, type,"
        " pfxlen, equiv, cc, origin_as_cc, equiv2) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "AS28000",
            "2001:4:112::/48",
            48,
            "arin",
            "28000",
            1,
            2,
            "ipv6",
            48,
            1.52587890625e-05,
            "US",
            "UY",
            65536,
        ),
    )
    conn.commit()
    conn.close()
    return path


class TestWriteCsv:
    def _rows(self, small_db, table, tmp_path):
        out = tmp_path / f"{table}.csv"
        with sqlite3.connect(small_db) as conn:
            n, bad = export.write_csv(conn, table, out)
        with out.open(newline="") as fh:
            return n, bad, list(csv.DictReader(fh))

    def test_typed_cleanup(self, small_db, tmp_path):
        n, bad, rows = self._rows(small_db, "numres", tmp_path)
        assert (n, bad) == (3, 0)
        assert rows[0]["orgid"] == "71316"  # stored as INTEGER by SQLite affinity
        assert rows[0]["date"] == "20000101"
        assert rows[1]["cc"] == rows[1]["date"] == rows[1]["orgid"] == ""  # '' → NULL
        assert rows[2]["date"] == ""  # 00000000 → NULL
        assert rows[2]["orgid"] == 'd98c,"q"'  # quoting round-trips

    def test_float_kept_exactly(self, small_db, tmp_path):
        _, _, rows = self._rows(small_db, "roadata", tmp_path)
        assert float(rows[0]["equiv"]) == 1.52587890625e-05
        assert rows[0]["origin_as2"] == "28000"

    def test_values_that_dont_fit_are_null_and_counted(self, tmp_path):
        # a legacy db imported delegated summary lines: 'summary' landed in `date`
        path = tmp_path / "legacy.db"
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE numres (id INTEGER PRIMARY KEY, rir text, date integer)")
            conn.execute("INSERT INTO numres (rir, date) VALUES ('lacnic', 'summary')")
            n, bad = export.write_csv(conn, "numres", tmp_path / "numres.csv")
        assert (n, bad) == (1, 1)


class TestExportCommand:
    def test_parquet_and_csv(self, small_db, tmp_path):
        result = runner.invoke(app, ["export", str(small_db), "--format", "parquet,csv"])
        assert result.exit_code == 0, result.output
        out = tmp_path / "netdata-20261110"
        assert sorted(p.name for p in out.iterdir()) == [
            "meta.parquet",
            "netdata-20261110.csv.tar.gz",
            "numres.parquet",
            "roadata.parquet",
        ]
        for t in ("numres", "roadata", "meta"):
            types = _parquet_types(out / f"{t}.parquet")
            assert types == {c: export.SCHEMA[t][c] for c in types}
        assert _pq(f"SELECT orgid, date, cc FROM '{out}/numres.parquet' ORDER BY id") == [
            ("71316", 20000101, "UY"),
            (None, None, None),
            ('d98c,"q"', None, "US"),
        ]
        with tarfile.open(out / "netdata-20261110.csv.tar.gz") as tar:
            assert sorted(tar.getnames()) == ["meta.csv", "numres.csv", "roadata.csv"]

    def test_legacy_db_without_new_tables_or_columns(self, tmp_path):
        path = tmp_path / "netdata-20170101.db"
        with sqlite3.connect(path) as conn:
            conn.execute(
                "CREATE TABLE roadata (id INTEGER PRIMARY KEY, origin_as text, maxlen integer)"
            )
            conn.execute("INSERT INTO roadata (origin_as, maxlen) VALUES ('ASN', 'Max Length')")
            conn.execute("INSERT INTO roadata (origin_as, maxlen) VALUES ('AS1', 24)")
        result = runner.invoke(app, ["export", str(path), "--format", "parquet"])
        assert result.exit_code == 0, result.output
        assert "1 values didn't fit" in result.output
        out = tmp_path / "netdata-20170101"
        assert [p.name for p in out.iterdir()] == ["roadata.parquet"]
        assert _pq(f"SELECT origin_as, maxlen FROM '{out}/roadata.parquet' ORDER BY id") == [
            ("ASN", None),
            ("AS1", 24),
        ]

    def test_output_dir_and_rerun_replaces(self, small_db, tmp_path):
        args = ["export", str(small_db), "--format", "csv", "--output-dir", str(tmp_path / "x")]
        assert runner.invoke(app, args).exit_code == 0
        stale = tmp_path / "x" / "netdata-20261110" / "stale.txt"
        stale.write_text("from an earlier run")
        assert runner.invoke(app, args).exit_code == 0
        assert not stale.exists()

    @pytest.mark.parametrize(
        ("args", "msg"),
        [
            (["--format", "jsonl"], "#12"),
            (["--format", ""], "no export format"),
        ],
    )
    def test_bad_arguments(self, small_db, args, msg):
        result = runner.invoke(app, ["export", str(small_db), *args])
        assert result.exit_code == 2
        assert msg in result.output

    def test_missing_db(self, tmp_path):
        result = runner.invoke(app, ["export", str(tmp_path / "nope.db"), "--format", "csv"])
        assert result.exit_code == 2

    def test_failure_leaves_nothing(self, small_db, tmp_path, monkeypatch):
        def boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(export, "csv_tarball", boom)
        result = runner.invoke(app, ["export", str(small_db), "--format", "parquet,csv"])
        assert result.exit_code == 1
        assert sorted(p.name for p in tmp_path.iterdir()) == ["netdata-20261110.db"]


class TestGetWithExport:
    def test_full_run_exports(self, serve, tmp_path):
        result = run_get("--export", "parquet", "--export", "csv")
        assert result.exit_code == 0, result.output
        out = _export_dir(tmp_path)
        assert out.name == built_db(tmp_path).stem
        with sqlite3.connect(built_db(tmp_path)) as conn:
            for t in export.tables(conn):
                n = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                assert _pq(f"SELECT count(*) FROM '{out}/{t}.parquet'") == [(n,)]
        types = _parquet_types(out / "riswhois.parquet")
        assert types["rovstatus"] == "VARCHAR" and types["rov_roas"] == "INTEGER"
        # exactly the db and its export dir: no staging leftovers
        assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [out.name, f"{out.name}.db"]

    def test_no_export_by_default(self, serve, tmp_path):
        assert run_get("--source", "delegated").exit_code == 0
        assert [p.suffix for p in (tmp_path / "out").iterdir()] == [".db"]

    def test_export_failure_publishes_nothing(self, serve, tmp_path, monkeypatch):
        def boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(export, "csv_to_parquet", boom)
        result = run_get("--source", "delegated", "--export", "parquet")
        assert result.exit_code == 1
        assert list((tmp_path / "out").iterdir()) == []

    def test_publish_failure_takes_the_db_back(self, serve, tmp_path, monkeypatch):
        def boom(self):
            raise OSError("rename failed")

        monkeypatch.setattr(export.Stage, "publish", boom)
        result = run_get("--source", "delegated", "--export", "csv")
        assert result.exit_code == 1
        assert list((tmp_path / "out").iterdir()) == []

    def test_planned_format_rejected_before_downloading(self, serve, tmp_path):
        result = run_get("--export", "duckdb")
        assert result.exit_code == 2
        assert "#13" in result.output
        assert not (tmp_path / "cache").exists()


def test_export_dir_naming():
    assert pipeline.export_dir(Path("var/netdata-20261110.db")) == Path("var/netdata-20261110")


def test_typed_schema_matches_spec():
    spec = (Path(__file__).parents[1] / "SPEC.md").read_text()
    section = spec[spec.index("### 5.7") : spec.index("## 6.")]
    documented = {}
    for table, cols in re.findall(r"^\| `(\w+)` \| (`.+) \|$", section, re.M):
        documented[table] = dict(re.findall(r"`(\w+)` (\w+)", cols))
    assert documented == export.SCHEMA
