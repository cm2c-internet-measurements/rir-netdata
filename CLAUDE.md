# CLAUDE.md

Guidance for Claude Code in this repo. **`SPEC.md` is the source of truth** for what the pipeline produces. Read it before changing anything that affects the output database. **`PLAN.md`** holds the staged implementation plan and its status. Update it when a stage lands.

## What this is

A batch pipeline that downloads the five RIRs' delegated-extended files, a Routinator ROA CSV and the RIPE RIS whois dumps. It enriches them and writes one SQLite file per run (`var/netdata-YYYYMMDD.db`), which is published as open data.

## Current state (Nov 2026)

- Branch `refactor-2026` is a **from-scratch Python 3 rewrite**. The legacy Python 2.7 code (`bin/`, `etc/`, `doc/`, `test/`, Pipfile, Dockerfile, Makefile) is **reference only**. It's slated for deletion, so don't fix or extend it.
- The legacy logic lives in two sibling repos, also reference only:
  - `rir-netdatalib` (`lacniclabs/netdata/{delegated,riperpki,riswhois}.py`, `lacniclabs/utils/addr.py`, `lacniclabs/etc/rirconfig.py`): re-implement its behavior here.
  - `cm2c-python-commons` (`sql3load`, `getfile`): **do not port or imitate**. Use native libraries instead.
  - Local checkouts: `../rir-netdatalib`, `../cm2c-python-commons`.
- The new package in `src/rir_netdata/` builds the full database. See `PLAN.md` for what's left.

## Stack

- Python ≥ 3.12, managed with **uv** (`pyproject.toml`, `uv.lock` committed).
- CLI: **typer** + **rich** (colored output, progress bars). Console script: `rir-netdata`.
- Tabular transforms: **petl** (stream rows, add derived fields with `addfield`, load with `appenddb`). Create tables with explicit DDL from SPEC §5 first; never let a library infer the schema.
- IP math: stdlib `ipaddress`. HTTP: `httpx` or `urllib`. Retries: **tenacity** decorators. Config: TOML via stdlib `tomllib`.
- Tests: **pytest**, offline only, using small fixture files under `tests/fixtures/`. Lint/format: **ruff**.

## Commands

```sh
uv sync                                   # install
uv run rir-netdata get                    # full run → var/netdata-YYYYMMDD.db
uv run rir-netdata get --source rpki      # single source
uv run pytest                             # tests (no network)
uv run ruff check . && uv run ruff format .
```

## Layout

```
src/rir_netdata/
  cli.py          # typer app
  config.py       # defaults + TOML override (all source URLs live here)
  fetch.py        # cached downloads with tenacity retries
  addr.py         # prefix → istart/iend/type/pfxlen/equiv (single implementation, shared)
  sources/        # delegated.py, rpki.py, riswhois.py — parse + derive, one per source
  enrich.py       # roadata cc / origin_as_cc
  progress.py     # rich progress bars (downloads, row loads, index, enrichment)
  pipeline.py     # orchestration: download all, then build atomically
  db.py           # DDL, atomic temp-file build + rename, meta table
tests/
```

## Hard rules

- **The output schema is a public contract.** Don't rename, retype or reorder columns, or change units, unless SPEC.md changes in the same commit. Any behavior change versus legacy goes in SPEC §7.
- **Units:** IPv4 `istart`/`iend` = address ints; **IPv6 = address >> 64 (/64 units)**; ASN = ASN. All ranges are inclusive. Never store full 128-bit ints, because SQLite integers are signed 64-bit.
- **Never publish a partial db.** Build into a temp file, rename only on full success, and exit non-zero otherwise.
- Tests and CI must never hit the network. Network sources are mocked or read from fixtures.
- No new data sources or features without a SPEC.md update first.

## Gotchas in the source data

- Delegated files have a version header line, `summary` lines and `#` comments. Skip them all, and record the header serial in `meta`.
- An IPv4 delegated `value` is an address **count** and isn't always a power of two. Compute `iend` from the count, not from a prefix length. If the block isn't CIDR-aligned, `prefix` is a range string `a.b.c.d-e.f.g.h`.
- `equiv` is always an integer floor, so sub-unit blocks get `0`.
- The delegated `opaque-id` (column `orgid`) is a string, but the DDL says `integer`, so SQLite stores LACNIC's all-digit ids as integers and everyone else's as text. Keep it that way, because it's the contract.
- `available` rows have 7 fields (no opaque-id), and `cc`/`date` are often empty strings.
- The Routinator CSV has a header row, and `origin_as` looks like `AS28000`.
- RIS dumps are gzipped, tab-separated, have comment/header lines, and `origin_as` can be an AS-set like `{1,2}`.
- The CC enrichment must match on address family and status `allocated`/`assigned`, and default to `'ZZ'`.

## Conventions

- Keep source modules pure (bytes/lines in → rows out). Do I/O in `fetch.py` and `db.py` so parsing stays testable from fixtures.
- Put user-facing output through rich. Use no bare `print`.
- Commit or push only when asked. Work happens on `refactor-2026`.
