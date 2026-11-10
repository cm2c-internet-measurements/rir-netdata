# Implementation plan: refactor-2026

The staged plan for the Python 3 rewrite described in `SPEC.md`. Each stage ends in a commit on `refactor-2026` with `ruff` and `pytest` green. Update the status column as stages land.

| Stage | Scope | Status |
|---|---|---|
| 0 | Skeleton | done |
| 1 | Address math | done |
| 2 | Output DB | done |
| 3 | Config + downloads | done |
| 4 | Delegated → `numres` | done |
| 5 | RPKI → `roadata`, RIS → `riswhois` | done |
| 6 | CC enrichment | done |
| 7 | Parity, packaging, cleanup | todo |

## Stage 0: Skeleton

- `uv init` with a src layout. `pyproject.toml` requires Python ≥ 3.12 and pulls in typer, rich, petl, httpx, tenacity, plus pytest and ruff as dev dependencies.
- A `rir-netdata` console script with `--version` and a stub `get`.
- ruff and pytest config, and a GitHub Actions workflow (`uv sync`, `ruff check`, `pytest`).
- **Done:** `uv run rir-netdata --version` works and CI is green.

## Stage 1: Address math (`addr.py`)

- One pure function from a prefix, or a delegated `block`/`length` pair, to `type`, `istart`, `iend`, `pfxlen`, `prefix` and `equiv`. Rules are in SPEC §4.1 and §5.5.
- Tests cover:
  - IPv4 CIDR blocks and non-aligned ranges (range-string `prefix`).
  - IPv6 in /64 units, with prefixes outside `2000::/3` giving 0.
  - ASN ranges with an inclusive end.
  - `equiv` legacy formulas per table, and `equiv2` (SPEC §5.6).
  - `badipv4`/`badipv6`.
  - The int64 bounds.
- **Done:** every rule in SPEC §4–5 has a test.

## Stage 2: Output DB (`db.py`)

- DDL for all four tables plus the `numres` index, copied verbatim from SPEC §5.
- Atomic build into a temp file and rename on success. On any error the temp file is removed.
- A helper for writing `meta` rows.
- **Done:** tests show a failure mid-run leaves no file, and the DDL matches SPEC.

## Stage 3: Config and downloads (`config.py`, `fetch.py`)

- Default URLs with an optional TOML override.
- httpx downloads with tenacity retries, a cache dir with freshness windows, SHA-256 of each file, and rich progress.
- Verify every default URL against the live servers (APNIC's path especially).
- **Done:** retry and cache tests pass against a mocked transport, and a manual fetch of all 8 URLs succeeds.

## Stage 4: Delegated → `numres` (`sources/delegated.py`)

- The parser skips `#` comments, the version header and `summary` lines, and captures the header serial for `meta`.
- Rows are loaded with petl.
- Fixtures are trimmed real lines per RIR, including ARIN's non-power-of-two blocks.
- **Done:** `rir-netdata get --source delegated` builds a real db, and row counts reconcile with the files' summary lines.

## Stage 5: RPKI → `roadata`, RIS → `riswhois`

- Parsers for both sources skip their header and comment lines. `origin_as2` is derived from `origin_as`.
- **Done:** each source builds on its own, both from fixtures and from a live run.

## Stage 6: CC enrichment (`enrich.py`)

- SQL fills `roadata.cc` and `roadata.origin_as_cc`. It matches on address family and `status IN ('allocated','assigned')`, and defaults to `'ZZ'`.
- The step is skipped with a warning when `numres` isn't part of the run.
- **Done:** tests cover a match, no match (`'ZZ'`), an IPv6 ROA against an IPv4 range, and ROAs from trust anchors other than LACNIC.

## Stage 7: Parity, packaging, cleanup

**Parity check: done on 2026-11-10** against the legacy `https://trantor.labs.lacnic.net/carlos/netdata/netdata-20261110.db.gz` (same date as a new run). Every difference traces to SPEC §7:

- **`numres`:** legacy has 5 version-header rows and 15 summary rows (fix 1). The records for LACNIC, ARIN, RIPE and AFRINIC are identical. APNIC differs by about 35 records because legacy used the older `ftp.lacnic.net` mirror copy, while the new run uses APNIC's own server (serial 20261111).
- **Computed columns on shared records:**
  - ASN and IPv6: identical.
  - IPv4: 3,771 non-CIDR blocks differ in `iend`/`prefix`, 3,360 of them also in `istart` (fixes 5 and 10). `equiv` differs for those blocks only (it was floor for sub-/24 blocks, and has since been reverted to the legacy formula, fix 11).
- **`roadata`:**
  - Legacy's single `badipv4` row is the CSV header (fix 2), and legacy has no `cc` columns (fix 14).
  - 61 ROAs exist only in legacy and 117 only in the new run, because the Routinator snapshots were taken at different times.
  - On the 1.03M shared ROAs, every computed column matches except IPv6 `equiv`. In legacy that was a fractional float. 192,290 rows briefly floored to 0, so the legacy float was restored and `equiv2` added (fix 11).
- **`riswhois`:**
  - Legacy has 2 all-NULL rows from blank lines (fix 3).
  - 411 rows exist only in legacy and 279 only in the new run, because the dumps were generated at different times.
  - On the 1.59M shared rows: 4 differ in `istart`/`iend` (fix 13) and 41 in `pfxlen` (fix 8).

- A full `rir-netdata get` run with a rich summary.
- A parity check against a legacy db, if one exists (otherwise against the source summary counts). Every difference must trace to a SPEC §7 item.
- A uv-based Dockerfile, a new Makefile (`build`/`push`/`run`/`test`), and a README rewritten from SPEC.
- Delete the legacy code: `bin/`, `etc/airflow`, `doc/`, the old `test/`, Pipfile, `requirements.txt` and the old Dockerfile.
- Open a PR to `master`.
