# rir-netdata — Specification

Status: **v2.0 (implemented on `refactor-2026`)** · Last updated: 2026-11-10 · Owner: Carlos M. Martinez

## 1. Purpose

`rir-netdata` is a batch pipeline. It downloads public Internet number-resource datasets, normalizes and enriches them, and writes **one self-contained SQLite3 file per run**: a daily snapshot that analysts can query with plain SQL.

The output is **published as open data**. Its schema is a public contract: column names, types and units must stay stable, and every change has to be deliberate and documented here.

## 2. Scope of the 2026 rewrite

- Rewrite from scratch in **Python 3**, managed with **uv**.
- Use a typer + rich CLI.
- **Same three data tables and the same column semantics** as the legacy pipeline (§5). Genuine bugs get fixed, and each fix is listed in §7.
- **No new data sources or analysis features.** The only additions are operational: a built-in CC enrichment step (§4.4), retries (§6), atomic output (§6) and the `meta` table (§5.4).
- The legacy code is **reference only**. Nothing from `cm2c-python-commons` is reused (its CSV→SQLite importer `sql3load` and its downloader `getfile` are replaced by native libraries). The RIR-specific logic from `rir-netdatalib` is re-implemented inside this repo.

### Out of scope (for now)

New sources (IANA, RDAP, ASPA, BGP tables), historical/backfill runs, loading into Elasticsearch or other services (the JSON Lines export of §5.7 is a file only), a whois-style query tool, and scheduling (Airflow and similar). All of these are removed from the repo; git history keeps them.

## 3. Inputs

All sources are fetched over HTTPS. URLs are **configurable** (§6), and the defaults point at each operator's own server.

| Source | Default URL(s) | Format | Target table |
|---|---|---|---|
| LACNIC delegated-extended | `https://ftp.lacnic.net/pub/stats/lacnic/delegated-lacnic-extended-latest` | `\|`-separated | `numres` |
| ARIN delegated-extended | `https://ftp.arin.net/pub/stats/arin/delegated-arin-extended-latest` | `\|`-separated | `numres` |
| RIPE NCC delegated-extended | `https://ftp.ripe.net/pub/stats/ripencc/delegated-ripencc-extended-latest` | `\|`-separated | `numres` |
| AFRINIC delegated-extended | `https://ftp.afrinic.net/pub/stats/afrinic/delegated-afrinic-extended-latest` | `\|`-separated | `numres` |
| APNIC delegated-extended | `https://ftp.apnic.net/stats/apnic/delegated-apnic-extended-latest` | `\|`-separated | `numres` |
| RPKI validated objects (Routinator) | `https://routinator.labs.lacnic.net/json` | Routinator JSON: `metadata`, `roas` (`asn`, `prefix`, `maxLength`, `ta`), `routerKeys`, `aspas` (`customer`, `providers`, `ta`) | `roadata`, `aspadata`, `aspa_providers` |
| RIPE RIS whois dump, IPv4 | `https://www.ris.ripe.net/dumps/riswhoisdump.IPv4.gz` | gzip, tab-separated | `riswhois` |
| RIPE RIS whois dump, IPv6 | `https://www.ris.ripe.net/dumps/riswhoisdump.IPv6.gz` | gzip, tab-separated | `riswhois` |

> The default URLs, the APNIC path in particular, must be verified against the live servers before release.

Only the `latest` snapshot of each source is supported. A run is "today's view of the world".

## 4. Processing

### 4.1 Delegated-extended → `numres`

- Parse records `registry|cc|type|start|value|date|status|opaque-id[|extensions…]`. Only the first 8 fields are used.
- **Skip non-data lines**: comments (`#`), the version header line (`2|<registry>|<serial>|…`) and summary lines (`<registry>|*|<type>|*|<count>|summary`). The header's serial/date is recorded in `meta`.
- Derived columns:
  - **ipv4:** `istart` = integer value of `start`; `iend = istart + value - 1`; `prefix` = CIDR (`a.b.c.d/n`) when the block is CIDR-aligned (count is a power of two and start is aligned to it), otherwise the inclusive range string `a.b.c.d-e.f.g.h`; `equiv` = size in /24 equivalents (§5.6).
  - **ipv6:** `istart`/`iend` = network/last address **shifted right 64 bits** (units of /64); `prefix` = `start/value`; `equiv` = size in /32 equivalents (§5.6).
  - **asn:** `istart` = first ASN; `iend = istart + value - 1` (**inclusive**); `prefix` = literal `'na/asn'`; `equiv` = `value`.

### 4.2 Routinator JSON → `roadata` (JSON since 2.2, issue #18)

- One row per element of `roas`, in Routinator's order: `origin_as` ← `asn`, `prefix` ← `prefix`, `maxlen` ← `maxLength`, `ta` ← `ta`. `routerKeys` are ignored.
- Until 2.1 this came from Routinator's `/csv` export. Both exports list the same ROAs in the same order (verified 2026-11-11: 1,033,123 rows, identical values and storage types), so `roadata` doesn't change. A configured URL that doesn't return Routinator JSON, such as the old `/csv`, fails the run with a clear error.
- `meta` gets the row `rpki-roas`, whose `source_serial` is Routinator's `metadata.generatedTime`.
- `origin_as` is kept as given (e.g. `AS28000`). `origin_as2` is the numeric part (`28000`).
- Derived columns: `istart`, `iend`, `type` and `pfxlen` follow the same rules as 4.1. `equiv` and `equiv2` follow §5.6.
- Unparseable prefixes get `type='badipv4'`/`'badipv6'` and `istart=iend=pfxlen=-1`, and are logged. This is the legacy behavior, kept.

### 4.3 RIS whois dumps → `riswhois`

- Concatenate the IPv4 and IPv6 dumps into one table. Skip comment and header lines.
- Derived columns: `type`, `istart`, `iend` and `pfxlen` follow the rules in 4.1. No `equiv` column (legacy schema).
- IPv6 prefixes outside `2000::/3` get `istart=iend=0`, as in legacy. `pfxlen` is still filled in (see §7).
- `rovstatus`, `rovreason` and `rov_roas` are filled by the ROV step (§4.5).

### 4.4 Enrichment: country codes on `roadata` (built-in)

This step runs after `numres` and `roadata` are loaded. It covers **ROAs from every trust anchor**, not only LACNIC's.

- `roadata.cc`: the `cc` of the `numres` row with **the same `type`** whose `[istart, iend]` contains the ROA's `istart`, restricted to `status IN ('allocated','assigned')`.
- `roadata.origin_as_cc`: the `cc` of the `numres` row with `type='asn'` that contains `origin_as2`, under the same status rule.
- `aspadata.asid_cc` (since 2.2): the `cc` of the `numres` row with `type='asn'` that contains `asid`, under the same status rule.
- If nothing matches, the value is `'ZZ'`.
- If a run doesn't include `numres` (single-source run), the step is skipped with a warning and these columns stay NULL.

### 4.5 Enrichment: RPKI route origin validation on `riswhois` (since 2.1, issue #8)

This step runs after `roadata` and `riswhois` are loaded. Every `riswhois` route gets an RFC 6811 validation state, computed against **all ROAs in `roadata`, from every trust anchor**.

- A ROA **covers** a route if the ROA's prefix contains the route's prefix (same address family, ROA prefix length ≤ route prefix length). A covering ROA **matches** if its ASN equals the route's origin AS, the route's prefix length is ≤ the ROA's `maxlen`, and the ASN is not 0. AS0 ROAs (RFC 6483, RFC 7607) cover routes but never match.
- `rovstatus`:
  - `notfound` if no ROA covers the route;
  - `valid` if at least one covering ROA matches;
  - `invalid` otherwise.
- `rovreason`: NULL unless `rovstatus` is `invalid`. Then, in order of precedence:
  1. `as_set` if the origin is an AS-set (e.g. `{40179}`). Following RFC 6811 strictly, an AS-set origin never matches, single-member sets included.
  2. `length` if some covering ROA has the route's origin ASN but its `maxlen` is shorter than the route's prefix length.
  3. `asn` otherwise.
- `rov_roas`: the number of covering ROAs (0 for `notfound`). Every trust anchor and AS0 ROAs count, and duplicate ROAs under two trust anchors count twice.
- Coverage is computed on the **real prefixes**, not on `istart`/`iend`. IPv6 `istart`/`iend` are in /64 units and can't tell apart prefixes longer than /64. Default routes and prefixes outside `2000::/3` are validated like any other; in practice no ROA covers them, so they come out `notfound`.
- Rows whose prefix couldn't be parsed (`type` not `ipv4`/`ipv6`) get NULL in all three columns.
- **Verified** against Routinator's validity API (`scripts/rov_crosscheck.py`): on 2026-11-10, 1,200 sampled routes agreed on status, reason and ROA count. Note that Routinator's own *description* calls a route "length"-invalid whenever no covering VRP fails on ASN alone. `rovreason` says `length` only when a covering ROA has the route's own ASN, as defined above, so with a wrong-ASN, too-short ROA we say `asn` and Routinator's text says length.
- If a run doesn't include `roadata` (e.g. `--source riswhois`), the step is skipped with a warning and all three columns stay NULL. `notfound` would falsely claim that no ROA exists.

### 4.6 Routinator JSON `aspas` → `aspadata` and `aspa_providers` (since 2.2, issue #16)

ASPA (Autonomous System Provider Authorization) objects come from the same Routinator export as the ROAs (§4.2), one per customer AS.

- One `aspadata` row per element of `aspas`, in Routinator's order:
  - `asid` ← `customer`, as a plain integer (`AS43` → 43);
  - `providers` ← `providers`, as AS numbers sorted ascending and joined with commas, without the `AS` prefix (`['AS6939', 'AS174']` → `'174,6939'`);
  - `ta` ← `ta`, the same trust-anchor names as `roadata.ta`;
  - `asid_cc` is filled by the enrichment step (§4.4).
- One `aspa_providers` row per (customer, provider) pair, with the same `asid` and `ta`, for joins such as "which ASes list AS174 as a provider?".
- **AS0** as a provider means the customer AS declares that it has no providers (ASPA profile, draft-ietf-sidrops-aspa-profile). It is kept as published: `providers = '0'` and an `aspa_providers` row with `provider = 0`.
- An AS number that isn't of the form `AS<digits>`, or an entry without `customer`, `providers` or `ta`, fails the run: Routinator always writes that form, so anything else means its format changed.
- An export without ASPAs (e.g. a validator with ASPA disabled) gives empty tables and a warning.
- `meta` gets the row `rpki-aspas`, sharing `url`, `sha256` and `source_serial` with `rpki-roas`. Its `row_count` is the number of ASPAs, not of provider pairs.
- ASPA *path verification* of `riswhois` routes isn't possible: the RIS whois dumps give only the origin AS, not the AS path.

## 5. Output

A single file, by default `var/netdata-YYYYMMDD.db` (UTC date of the run). The output directory and basename are configurable.

### 5.1 `numres`

```sql
CREATE TABLE numres (id INTEGER PRIMARY KEY, rir text, cc text, type text, block text, length integer,
  date integer, status text, orgid integer, istart INTEGER, iend INTEGER, prefix VARCHAR(80), equiv INTEGER);
```
`orgid` is declared `integer` for compatibility, but holds the RIR's opaque-id. Because of SQLite type affinity, all-digit ids (LACNIC's) are stored as integers and all others (hex, UUID) as text, exactly as in legacy. Rows without an opaque-id get NULL; rows with an empty one keep `''`. No RIR currently uses all-digit ids with leading zeros, so nothing is lost.

The table gets an index for range lookups. It doesn't change the visible schema:

```sql
CREATE INDEX numres_type_range ON numres (type, istart, iend);
```

### 5.2 `roadata`

```sql
CREATE TABLE roadata (id INTEGER PRIMARY KEY, origin_as text, prefix text, maxlen integer, ta text,
  origin_as2 VARCHAR(10), istart UNSIGNED BIG INT, iend UNSIGNED BIG INT, type VARCHAR(5), pfxlen INTEGER,
  equiv INTEGER, cc CHAR(2), origin_as_cc CHAR(2), equiv2 INTEGER);
```

### 5.3 `riswhois`

```sql
CREATE TABLE riswhois (id INTEGER PRIMARY KEY, origin_as text, prefix text, viewed_by integer,
  istart UNSIGNED BIG INT, iend UNSIGNED BIG INT, type VARCHAR(5), pfxlen INTEGER,
  rovstatus text, rovreason text, rov_roas integer);
```

The `rov*` columns were added in 2.1 and are appended last, so positional `SELECT *` consumers are unaffected.

### 5.4 `meta` (new)

There is one row per table loaded from each fetched source file, and run-level values are repeated on every row. A file that feeds several tables gives several rows with the same `url`, `fetched_at_utc` and `sha256`.

```sql
CREATE TABLE meta (source text, url text, fetched_at_utc text, source_serial text, row_count integer,
  sha256 text, tool_version text, run_started_at_utc text);
```

### 5.5 Unit conventions (the contract)

| Type | `istart` / `iend` unit | `equiv` unit |
|---|---|---|
| ipv4 | single address (32-bit int) | /24 |
| ipv6 | /64 (address >> 64) | /32 |
| asn | ASN | 1 ASN |

All ranges are **inclusive**. Values must fit in SQLite's signed 64-bit integer, which is why IPv6 is stored in /64 units.

### 5.6 `equiv` and `equiv2`

`equiv` reproduces the legacy formula of each table **exactly**, so existing analyst scripts keep giving the same numbers. `n` is `iend - istart + 1` in the table's units (§5.5).

| Table | Type | `equiv` | Example |
|---|---|---|---|
| `numres` | ipv4 | `(iend - istart) // 256 + 1`: any partial /24 counts as one | /25 → 1, /16 → 256 |
| `numres` | ipv6 | `n // 2**32`, floor | /48 → 0, /32 → 1 |
| `numres` | asn | count of ASNs | |
| `roadata` | ipv4 | `n // 256`, floor | /25 → 0, /22 → 4 |
| `roadata` | ipv6 | `n / 2**32` as a **float**; 0 outside `2000::/3` | /48 → 1.52587890625e-05 |

The roadata IPv6 formula counts anything longer than a /64 as one /64, so a /128 gives `2**-32`. That's a legacy quirk, kept on purpose.

`roadata.equiv2` (new) is the exact integer size. For **IPv4** it is the number of whole /24s, the same as `equiv`. For **IPv6** it is the number of whole **/64s**: `2**(64 - pfxlen)`, or 0 for prefixes longer than /64 and for anything outside `2000::/3`. So a /48 is 65536, a /32 is 4294967296 and a /128 is 0. Bad prefixes get 0. `equiv2` is the last column, so positional `SELECT *` consumers are unaffected.

### 5.7 Exports (since 2.1)

The SQLite database is always produced and remains the source of truth. Exports are optional copies of it, in other formats, requested with `get --export …` or made afterwards from any existing db with `rir-netdata export DB --format …`.

| Format | `--export` / `--format` value | Output | Status |
| --- | --- | --- | --- |
| Parquet | `parquet` | `<db stem>/<table>.parquet`, one file per table, zstd | implemented (#10) |
| CSV | `csv` | `<db stem>/<db stem>.csv.tar.gz`, containing `<table>.csv` per table | implemented (#11) |
| JSON Lines | `jsonl` | `<db stem>/<db stem>.jsonl.tar.gz`, containing `<table>.jsonl` per table | implemented (#12) |
| DuckDB | `duckdb` | `<db stem>/<db stem>.duckdb`, with every table | implemented (#13) |
| Compressed SQLite | `sqlite.gz` | `<db stem>.db.gz`, next to the `.db` | implemented (#14) |

`<db stem>` is the database file name without `.db`, so `var/netdata-20261110.db` exports into `var/netdata-20261110/`. Every table present in the db is exported, `meta` included. With `rir-netdata export --output-dir DIR`, both the export directory and the `.db.gz` go in `DIR`. A run that asks only for `sqlite.gz` creates no export directory.

**`sqlite.gz`** is the finished `.db` file, byte for byte, as plain gzip (level 6, the `gzip(1)` default), readable with `gunzip` or `zcat`. The gzip header keeps the original file name. It is not typed, because it is the SQLite file itself; everything below applies to the other formats.

**Typed schema.** Exports have one type per column, unlike SQLite. Values are cleaned on the way out:

- empty strings become NULL;
- `numres.date` `''` and `00000000` (stored as 0) become NULL;
- `orgid` is always a string;
- `origin_as2` is an integer.

Columns not listed below, e.g. from a legacy db, are exported as VARCHAR. In a legacy db, a value that doesn't fit its column's type, such as the imported delegated summary lines or the Routinator header row, is exported as NULL and counted in a warning.

| Table | Column and type |
| --- | --- |
| `numres` | `id` BIGINT · `rir` VARCHAR · `cc` VARCHAR · `type` VARCHAR · `block` VARCHAR · `length` BIGINT · `date` INTEGER · `status` VARCHAR · `orgid` VARCHAR · `istart` BIGINT · `iend` BIGINT · `prefix` VARCHAR · `equiv` BIGINT |
| `roadata` | `id` BIGINT · `origin_as` VARCHAR · `prefix` VARCHAR · `maxlen` INTEGER · `ta` VARCHAR · `origin_as2` BIGINT · `istart` BIGINT · `iend` BIGINT · `type` VARCHAR · `pfxlen` INTEGER · `equiv` DOUBLE · `cc` VARCHAR · `origin_as_cc` VARCHAR · `equiv2` BIGINT |
| `aspadata` | `id` BIGINT · `asid` BIGINT · `providers` VARCHAR · `ta` VARCHAR · `asid_cc` VARCHAR |
| `aspa_providers` | `asid` BIGINT · `provider` BIGINT · `ta` VARCHAR |
| `riswhois` | `id` BIGINT · `origin_as` VARCHAR · `prefix` VARCHAR · `viewed_by` INTEGER · `istart` BIGINT · `iend` BIGINT · `type` VARCHAR · `pfxlen` INTEGER · `rovstatus` VARCHAR · `rovreason` VARCHAR · `rov_roas` INTEGER |
| `meta` | `source` VARCHAR · `url` VARCHAR · `fetched_at_utc` VARCHAR · `source_serial` VARCHAR · `row_count` BIGINT · `sha256` VARCHAR · `tool_version` VARCHAR · `run_started_at_utc` VARCHAR |

**CSV dialect:**

- UTF-8, with a header row;
- `,` as the delimiter and `\n` line endings;
- RFC 4180 quoting, applied only when needed;
- **an empty field means NULL**. This is lossless, because no exported value is an empty string.

**How they're made.** Python streams each table out of SQLite with the typed cleanup into CSV. DuckDB reads those CSVs with the explicit types above and writes Parquet, JSON Lines and the DuckDB database. No DuckDB extension and no network access are needed.

**JSON Lines.** One JSON object per row, UTF-8, `\n`-terminated. Every column is a key, in table order, even when its value is `null`. Integers and doubles are JSON numbers, and NULL is `null`. IPv6 `istart`/`iend` go up to 2^62, beyond the 2^53 that a JavaScript `JSON.parse` or a double can hold exactly. jq ≥ 1.7, Python and Elasticsearch `long` fields keep them exact.

**DuckDB database.** It is written by DuckDB 1.5, so DuckDB 1.5 and every later version, 2.x included, can open it. The tables have the same columns, order and types as Parquet. They have no primary key and no indexes: DuckDB's per-block min/max statistics already serve range lookups like `istart <= x AND iend >= x`, and an index like SQLite's `numres (type, istart, iend)` made the file 50% larger without making that query faster (#13).

**Atomicity.** Exports are staged in a temp directory next to their destination. A run publishes the export directory, the `.db.gz` and the `.db` only when **everything**, every requested format included, has succeeded. If an export fails, nothing is published, not even the `.db`, and the run exits non-zero. A rerun on the same day replaces the earlier export directory.

### 5.8 `aspadata` and `aspa_providers` (since 2.2, issue #16)

```sql
CREATE TABLE aspadata (id INTEGER PRIMARY KEY, asid integer, providers text, ta text, asid_cc CHAR(2));
CREATE TABLE aspa_providers (asid integer, provider integer, ta text);
```

`aspa_providers` gets an index for "who lists this provider" lookups:

```sql
CREATE INDEX aspa_providers_provider ON aspa_providers (provider);
```

## 6. Operational behavior

- **CLI:** `rir-netdata get [--source delegated|rpki|riswhois|all] [--rir lacnic|arin|ripencc|afrinic|apnic|all] [--output-dir var] [--basename netdata] [--config FILE] [--export FORMATS]`, and `rir-netdata export DB --format FORMATS [--output-dir DIR]` (§5.7). It uses rich progress and status output.
- **Config:** built-in defaults, optionally overridden by a TOML file (`--config`). All source URLs, retry limits and the cache directory are configurable.
- **Retries:** every download uses `tenacity` with exponential backoff. Attempts and maximum wait come from config.
- **Atomicity:** the run builds into a temp file next to the target. If every requested source and step succeeds, the temp file is renamed into place. Otherwise the temp file is deleted, the run exits non-zero, and no partial db is ever published.
- **Compression:** downloads ask for compressed transfer (`Accept-Encoding: gzip, deflate`) and are stored decompressed, so the cache and `meta.sha256` always refer to the content. Routinator's JSON is about 5 MB on the wire against 90 MB decompressed (issue #21).
- **Download cache:** raw downloads go to a cache dir (default `tmp/`). A file younger than its freshness window is reused: 1 h for delegated and RPKI, 24 h for RIS, matching legacy.
- **Packaging:** uv project with a `rir-netdata` console script, plus a Dockerfile built with uv. The container entrypoint is `rir-netdata get`.

## 7. Deliberate deviations from the legacy pipeline (bug fixes)

1. Delegated version header and `summary` lines are no longer imported as `numres` rows.
2. The Routinator CSV header row is no longer imported as a `badipv4` row.
3. RIS dump comment and header lines are no longer imported as junk rows.
4. ASN `iend` is inclusive (`start + count - 1`). `rir-netdatalib` already does this; old docs and builds did not.
5. IPv4 `istart` is the delegated start address and `iend = istart + count - 1`, which is correct for non-power-of-two and unaligned allocations. Legacy derived a CIDR from `log2(count)` and then masked it to a network boundary, so for 3,771 blocks (mostly ARIN) it stored a wrong `iend`, and for 3,360 of those a wrong `istart` too.
6. CC enrichment really writes `'ZZ'` on no match: legacy set `'ZZ'` and then overwrote it with NULL. It also matches on the exact address family. Legacy only excluded ASNs, which was safe in practice because IPv4 and IPv6 values never collide numerically, so this is a robustness fix rather than a change in output.
7. CC enrichment covers all trust anchors, not only LACNIC.
8. RIS IPv6 outside `2000::/3`: `pfxlen` is now filled in (legacy set it to 0).
9. The output filename date is the run's UTC date. There is no `--date` option, because it only ever applied to one of the three sources.
10. IPv4 `prefix` for delegations that aren't CIDR-aligned is a range string `a.b.c.d-e.f.g.h`, so `prefix` never claims space that wasn't delegated. Legacy wrote a CIDR derived from `log2(count)`.
11. `equiv` is unchanged from legacy in every table, including its per-table inconsistencies (§5.6). Floor rounding everywhere was decided and then reverted on 2026-11-10, because it zeroed 81% of IPv6 ROAs and would break existing scripts. The new `roadata.equiv2` column gives an exact integer size instead (/24s for IPv4, /64s for IPv6).
12. `numres` has an index on `(type, istart, iend)`.
13. IPv6 global unicast is tested with real `2000::/3` containment. Legacy tested `prefix.startswith("2")`, which wrongly zeroed `3xxx:` prefixes and computed values for short forms like `2a0::` (= `02a0::`). This affected 4 RIS rows on 2026-11-10.
14. `roadata.cc` and `roadata.origin_as_cc` actually exist in the published file. The legacy README documented them, but the production databases never had these columns, because the manual enrichment SQL was never run there.
15. `riswhois.rovstatus`, `rovreason` and `rov_roas` (since 2.1, issue #8) are new. Legacy had no route origin validation (§4.5).
16. Exports to Parquet, CSV, JSON Lines, DuckDB and `.db.gz` (since 2.1, §5.7) are new. Legacy only produced the SQLite file.
17. `roadata` comes from Routinator's JSON instead of its CSV (since 2.2, §4.2), with identical rows. The `meta` row for it is named `rpki-roas` instead of `rpki` (2.0–2.1), and its `source_serial` is filled in. `meta` is new in v2, so legacy scripts aren't affected.
18. The `aspadata` and `aspa_providers` tables (since 2.2, §4.6, §5.8) are new. Legacy had no ASPA data.

## 8. Open questions

None at the moment.

Resolved on 2026-11-10: the IPv4 range-string `prefix` and the `numres` index (§7 items 10 and 12). `equiv` keeps the legacy formulas, and the new column `equiv2` gives exact integer sizes (§5.6, §7 item 11).
