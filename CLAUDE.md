# CLAUDE.md

Guidance for Claude Code in this repo. **`SPEC.md` is the source of truth** for what the pipeline produces. Read it before changing anything that affects the output database. **`PLAN.md`** holds the staged implementation plan and its status. Update it when a stage lands.

## What this is

A batch pipeline that downloads the five RIRs' delegated-extended files, a Routinator ROA CSV and the RIPE RIS whois dumps. It enriches them and writes one SQLite file per run (`var/netdata-YYYYMMDD.db`), which is published as open data.

## History

- v2 (Nov 2026, branch `refactor-2026`) is a from-scratch Python 3 rewrite. It replaced the legacy Python 2.7 pipeline, which is gone from the tree but kept in git history (anything before the "Stage 7" commits).
- The legacy logic also lives in two sibling repos, **reference only**:
  - `rir-netdatalib`: its behavior is re-implemented here.
  - `cm2c-python-commons`: **do not port or imitate**.
  - Local checkouts: `../rir-netdatalib`, `../cm2c-python-commons`.
- When comparing against legacy output, use a published legacy db (see the parity notes in `PLAN.md`). Every difference must trace to SPEC §7.

## Stack

- Python ≥ 3.12, managed with **uv** (`pyproject.toml`, `uv.lock` committed).
- CLI: **typer** + **rich** (colored output, progress bars). Console script: `rir-netdata`.
- Exports: **DuckDB** (`read_csv` with explicit types → `COPY … TO` parquet/json, `CREATE TABLE … AS` in a `.duckdb`). Never use its `sqlite` extension, because it downloads at runtime. **Pinned to 1.5.x** (`<2`): DuckDB 2.0 wheels crash on CPUs without AVX2 (the QEMU VMs we build and run on), and a `.duckdb` file written by 2.0 can't be opened by DuckDB 1.x. Import it only inside the export functions, never at module level; a test enforces this.
- Tabular transforms: **petl** (stream rows with `fromcsv`/`select`/`cut`, derive columns in one `rowmap`, load with `appenddb`). Create tables with explicit DDL from SPEC §5 first; never let a library infer the schema.
- IP math: stdlib `ipaddress`. HTTP: `httpx`. Retries: **tenacity** decorators. Config: TOML via stdlib `tomllib`.
- Tests: **pytest**, offline only, using small fixture files under `tests/fixtures/`. Lint/format: **ruff**.

## Commands

```sh
uv sync                                   # install
uv run rir-netdata get                    # full run → var/netdata-YYYYMMDD.db
uv run rir-netdata get --source rpki      # single source
uv run pytest                             # tests (no network)
uv run pytest -m network                  # also check that the live source URLs answer
uv run ruff check . && uv run ruff format .
make help                                 # test / run / build / push / image-run (ENGINE=podman)
```

## Layout

```
src/rir_netdata/
  cli.py          # typer app
  config.py       # defaults + TOML override (all source URLs live here)
  fetch.py        # cached downloads with tenacity retries
  addr.py         # prefix → istart/iend/type/pfxlen/equiv/equiv2 (single implementation, shared)
  sources/        # delegated.py, rpki.py, riswhois.py — parse + derive, one per source
  enrich.py       # roadata cc / origin_as_cc
  rov.py          # riswhois rovstatus / rovreason / rov_roas (RFC 6811, SPEC §4.5)
  export.py       # typed CSV → Parquet / .csv.tar.gz / .jsonl.tar.gz / .duckdb, plus .db.gz; staged + published atomically (SPEC §5.7)
  progress.py     # rich progress bars (downloads, row loads, index, enrichment)
  pipeline.py     # orchestration: download all, then build atomically
  db.py           # DDL, atomic temp-file build + rename, meta table
tests/            # offline tests; fixtures/ are trimmed real source files
Dockerfile        # uv multi-stage image; WORKDIR /data (var/ = output, tmp/ = cache)
Makefile
etc/*_region.json # per-region country lists, not used by the pipeline (yet)
```

## Hard rules

- **The output schema is a public contract.** Don't rename, retype or reorder columns, or change units, unless SPEC.md changes in the same commit. Any behavior change versus legacy goes in SPEC §7.
- **Units:** IPv4 `istart`/`iend` = address ints; **IPv6 = address >> 64 (/64 units)**; ASN = ASN. All ranges are inclusive. Never store full 128-bit ints, because SQLite integers are signed 64-bit.
- **Never publish a partial db.** Build into a temp file, rename only on full success, and exit non-zero otherwise.
- Tests and CI must never hit the network. Network sources are mocked or read from fixtures.
- No new data sources or features without a SPEC.md update first.
- The export typed schema (`export.SCHEMA`) and the SPEC §5.7 table are kept in sync by a test. Change both together.
- Features are tracked as GitHub issues (sub-issues per piece). Record decisions in the issue, and reference it in commits and PRs.

## Gotchas in the source data

- Delegated files have a version header line, `summary` lines and `#` comments. Skip them all, and record the header serial in `meta`.
- An IPv4 delegated `value` is an address **count** and isn't always a power of two. Compute `iend` from the count, not from a prefix length. If the block isn't CIDR-aligned, `prefix` is a range string `a.b.c.d-e.f.g.h`.
- `equiv` copies the **legacy formula of each table exactly** (SPEC §5.6). The formulas aren't consistent across tables, on purpose, for compatibility. Don't "fix" them. `roadata.equiv2` is the exact integer size (/24s or /64s).
- The delegated `opaque-id` (column `orgid`) is a string, but the DDL says `integer`, so SQLite stores LACNIC's all-digit ids as integers and everyone else's as text. Keep it that way, because it's the contract.
- `available` rows have 7 fields (no opaque-id), and `cc`/`date` are often empty strings.
- The Routinator CSV has a header row, and `origin_as` looks like `AS28000`.
- RIS dumps are gzipped, tab-separated, and have `%` comment lines and a blank line. `origin_as` can be an AS-set like `{40179}`, and `::/0` and other prefixes outside `2000::/3` appear.
- The CC enrichment must match on address family and status `allocated`/`assigned`, and default to `'ZZ'`. Its fast nearest-start lookup is exact only because allocated/assigned delegations don't overlap within a type. If that ever changes, `enrich.py` needs revisiting.
- ROV must compare **full prefixes**, never `istart`/`iend` alone: IPv6 `istart` is in /64 units, and ROAs and routes go up to /128. ROAs overlap heavily (nested), so the nearest-start trick from `enrich.py` does **not** apply. `rov.py` indexes ROAs by (family, length, network) instead.
- To check ROV against Routinator after changing `rov.py`, run `uv run python scripts/rov_crosscheck.py var/netdata-*.db`. It hits the network.

## Conventions

- Keep source modules pure (bytes/lines in → rows out). Do I/O in `fetch.py` and `db.py` so parsing stays testable from fixtures.
- Put user-facing output through rich. Use no bare `print`.
- Commit or push only when asked. Branch off `master` for changes.
