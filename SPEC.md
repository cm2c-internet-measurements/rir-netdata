# rir-netdata — Specification

Status: **draft for the `refactor-2026` rewrite** · Last updated: 2026-11-10 · Owner: Carlos M. Martinez

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

New sources (IANA, RDAP, ASPA, BGP tables), historical/backfill runs, exports to Elastic/JSON, a whois-style query tool, and scheduling (Airflow and similar). All of these are removed from the repo; git history keeps them.

## 3. Inputs

All sources are fetched over HTTPS. URLs are **configurable** (§6), and the defaults point at each operator's own server.

| Source | Default URL(s) | Format | Target table |
|---|---|---|---|
| LACNIC delegated-extended | `https://ftp.lacnic.net/pub/stats/lacnic/delegated-lacnic-extended-latest` | `\|`-separated | `numres` |
| ARIN delegated-extended | `https://ftp.arin.net/pub/stats/arin/delegated-arin-extended-latest` | `\|`-separated | `numres` |
| RIPE NCC delegated-extended | `https://ftp.ripe.net/pub/stats/ripencc/delegated-ripencc-extended-latest` | `\|`-separated | `numres` |
| AFRINIC delegated-extended | `https://ftp.afrinic.net/pub/stats/afrinic/delegated-afrinic-extended-latest` | `\|`-separated | `numres` |
| APNIC delegated-extended | `https://ftp.apnic.net/stats/apnic/delegated-apnic-extended-latest` | `\|`-separated | `numres` |
| RPKI validated ROAs | `https://routinator.labs.lacnic.net/csv` | CSV with header `ASN,IP Prefix,Max Length,Trust Anchor` | `roadata` |
| RIPE RIS whois dump, IPv4 | `https://www.ris.ripe.net/dumps/riswhoisdump.IPv4.gz` | gzip, tab-separated | `riswhois` |
| RIPE RIS whois dump, IPv6 | `https://www.ris.ripe.net/dumps/riswhoisdump.IPv6.gz` | gzip, tab-separated | `riswhois` |

> The default URLs, the APNIC path in particular, must be verified against the live servers before release.

Only the `latest` snapshot of each source is supported. A run is "today's view of the world".

## 4. Processing

### 4.1 Delegated-extended → `numres`

- Parse records `registry|cc|type|start|value|date|status|opaque-id[|extensions…]`. Only the first 8 fields are used.
- **Skip non-data lines**: comments (`#`), the version header line (`2|<registry>|<serial>|…`) and summary lines (`<registry>|*|<type>|*|<count>|summary`). The header's serial/date is recorded in `meta`.
- Derived columns:
  - **ipv4:** `istart` = integer value of `start`; `iend = istart + value - 1`; `prefix` = CIDR (`a.b.c.d/n`) when the block is CIDR-aligned (count is a power of two and start is aligned to it), otherwise the inclusive range string `a.b.c.d-e.f.g.h`; `equiv` = size in /24 equivalents.
  - **ipv6:** `istart`/`iend` = network/last address **shifted right 64 bits** (units of /64); `prefix` = `start/value`; `equiv` = size in /32 equivalents.
  - **`equiv` rounding (all tables):** integer **floor**, so blocks smaller than one unit (e.g. an IPv4 /25 or an IPv6 /48) get `0`.
  - **asn:** `istart` = first ASN; `iend = istart + value - 1` (**inclusive**); `prefix` = literal `'na/asn'`; `equiv` = `value`.

### 4.2 Routinator CSV → `roadata`

- Skip the header row.
- `origin_as` is kept as given (e.g. `AS28000`). `origin_as2` is the numeric part (`28000`).
- Derived columns: `istart`, `iend`, `type`, `pfxlen` and `equiv` follow the same rules as 4.1.
- Unparseable prefixes get `type='badipv4'`/`'badipv6'` and `istart=iend=pfxlen=-1`, and are logged. This is the legacy behavior, kept.

### 4.3 RIS whois dumps → `riswhois`

- Concatenate the IPv4 and IPv6 dumps into one table. Skip comment and header lines.
- Derived columns: `type`, `istart`, `iend` and `pfxlen` follow the rules in 4.1. No `equiv` column (legacy schema).
- IPv6 prefixes outside `2000::/3` get `istart=iend=0`, as in legacy. `pfxlen` is still filled in (see §7).

### 4.4 Enrichment: country codes on `roadata` (built-in)

This step runs after `numres` and `roadata` are loaded. It covers **ROAs from every trust anchor**, not only LACNIC's.

- `roadata.cc`: the `cc` of the `numres` row with **the same `type`** whose `[istart, iend]` contains the ROA's `istart`, restricted to `status IN ('allocated','assigned')`.
- `roadata.origin_as_cc`: the `cc` of the `numres` row with `type='asn'` that contains `origin_as2`, under the same status rule.
- If nothing matches, the value is `'ZZ'`.
- If a run doesn't include `numres` (single-source run), the step is skipped with a warning and both columns stay NULL.

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
  equiv INTEGER, cc CHAR(2), origin_as_cc CHAR(2));
```

### 5.3 `riswhois`

```sql
CREATE TABLE riswhois (id INTEGER PRIMARY KEY, origin_as text, prefix text, viewed_by integer,
  istart UNSIGNED BIG INT, iend UNSIGNED BIG INT, type VARCHAR(5), pfxlen INTEGER);
```

### 5.4 `meta` (new)

There is one row per fetched source file, and run-level values are repeated on every row.

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

## 6. Operational behavior

- **CLI:** `rir-netdata get [--source delegated|rpki|riswhois|all] [--rir lacnic|arin|ripencc|afrinic|apnic|all] [--output-dir var] [--basename netdata] [--config FILE]`. It uses rich progress and status output.
- **Config:** built-in defaults, optionally overridden by a TOML file (`--config`). All source URLs, retry limits and the cache directory are configurable.
- **Retries:** every download uses `tenacity` with exponential backoff. Attempts and maximum wait come from config.
- **Atomicity:** the run builds into a temp file next to the target. If every requested source and step succeeds, the temp file is renamed into place. Otherwise the temp file is deleted, the run exits non-zero, and no partial db is ever published.
- **Download cache:** raw downloads go to a cache dir (default `tmp/`). A file younger than its freshness window is reused: 1 h for delegated and RPKI, 24 h for RIS, matching legacy.
- **Packaging:** uv project with a `rir-netdata` console script, plus a Dockerfile built with uv. The container entrypoint is `rir-netdata get`.

## 7. Deliberate deviations from the legacy pipeline (bug fixes)

1. Delegated version header and `summary` lines are no longer imported as `numres` rows.
2. The Routinator CSV header row is no longer imported as a `badipv4` row.
3. RIS dump comment and header lines are no longer imported as junk rows.
4. ASN `iend` is inclusive (`start + count - 1`). `rir-netdatalib` already does this; old docs and builds did not.
5. IPv4 `iend = istart + count - 1`, which is correct for non-power-of-two allocations. Legacy derived it from `log2(count)`.
6. CC enrichment really writes `'ZZ'` on no match: legacy set `'ZZ'` and then overwrote it with NULL. It also matches on the exact address family. Legacy only excluded ASNs, which was safe in practice because IPv4 and IPv6 values never collide numerically, so this is a robustness fix rather than a change in output.
7. CC enrichment covers all trust anchors, not only LACNIC.
8. RIS IPv6 outside `2000::/3`: `pfxlen` is now filled in (legacy set it to 0).
9. The output filename date is the run's UTC date. There is no `--date` option, because it only ever applied to one of the three sources.
10. IPv4 `prefix` for delegations that aren't CIDR-aligned is a range string `a.b.c.d-e.f.g.h`, so `prefix` never claims space that wasn't delegated. Legacy wrote a CIDR derived from `log2(count)`.
11. `equiv` is an integer floor everywhere. Legacy was inconsistent: a delegated IPv4 /25 gave 1, a roadata /25 gave 0, and roadata IPv6 was a float.
12. `numres` has an index on `(type, istart, iend)`.

## 8. Open questions

None at the moment.

Resolved on 2026-11-10: the IPv4 range-string `prefix`, floor rounding for `equiv`, and the `numres` index. See §7 items 10–12.
