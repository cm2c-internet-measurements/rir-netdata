# RIR NETDATA

A pipeline that builds a daily SQLite snapshot of Internet number-resource data. Each run writes one self-contained file, `var/netdata-YYYYMMDD.db`, with:

| Table | Contents | Source |
| --- | --- | --- |
| `numres` | Delegations from all five RIRs (IPv4, IPv6, ASN) | RIR delegated-extended files |
| `roadata` | Validated RPKI ROAs, with country codes for each prefix and origin AS | Routinator CSV export |
| `riswhois` | Origin AS for each prefix seen in BGP | RIPE RIS whois dumps (IPv4 and IPv6) |
| `meta` | Provenance: one row per source file (URL, fetch time, serial, rows, SHA-256) | the run itself |

Every table gets convenience columns that make range queries simple: `istart`/`iend` (inclusive integer ranges), `type`, `pfxlen`, `prefix` and `equiv` (size in /24 or /32 equivalents).

The database is published as open data, and its schema is a stable contract. **[SPEC.md](SPEC.md)** documents every column, unit and rule, and lists each deliberate difference from the legacy (2015–2025) pipeline.

*Author:* Carlos M. Martinez (<carlos@lacnic.net>)

## Quick start

Requires [uv](https://docs.astral.sh/uv/). uv installs Python ≥ 3.12 if needed.

```sh
uv sync
uv run rir-netdata get          # all sources → var/netdata-YYYYMMDD.db
```

A full run takes well under a minute on a good connection and produces a file of about 250 MB. Progress bars show each download, load and enrichment step. The run is atomic: if any source fails after retries, the command exits non-zero and **no database is written**.

### Options

```text
rir-netdata get [--source all|delegated|rpki|riswhois]
                [--rir all|lacnic|arin|ripencc|afrinic|apnic]
                [--output-dir var] [--basename netdata]
                [--config FILE]
```

Country codes in `roadata` come from `numres`, so they're only filled in when the delegated files are part of the run. A `--source rpki` run leaves them NULL and prints a warning.

### Configuration

The defaults point at each operator's own server over HTTPS. To change source URLs, retries, freshness windows or the cache directory, pass a TOML file with `--config`. Every key is optional, and an unknown key is an error:

```toml
cache_dir = "/var/cache/netdata"

[retry]
attempts = 5
max_wait_seconds = 60

[freshness_seconds]   # reuse cached downloads younger than this
delegated = 3600
rpki = 3600
riswhois = 86400

[sources.delegated]
lacnic = "https://ftp.lacnic.net/pub/stats/lacnic/delegated-lacnic-extended-latest"

[sources.rpki]
url = "https://routinator.labs.lacnic.net/csv"
```

## Container

```sh
make build                       # or: make build ENGINE=podman
make image-run                   # database → ./var, download cache → ./tmp
```

Or directly:

```sh
docker run --rm -v "$PWD/var:/data/var" -v "$PWD/tmp:/data/tmp" carlosm3012/rir-netdata:latest
podman run --rm -v "$PWD/var:/data/var" -v "$PWD/tmp:/data/tmp" localhost/carlosm3012/rir-netdata:latest
```

Mounting `/data/tmp` is optional, but it keeps downloads cached between runs. Any extra arguments replace the default `get`: for example, `... rir-netdata:latest get --source delegated`.

## Example queries

```sql
-- Which delegation contains 200.7.84.1, and from which RIR?
SELECT rir, cc, prefix, status FROM numres
WHERE type = 'ipv4' AND istart <= 3355923457 AND iend >= 3355923457;

-- ROAs and /24s covered, by the country the prefix is delegated to
SELECT cc, count(*) AS roas, sum(equiv) AS slash24s
FROM roadata WHERE type = 'ipv4' GROUP BY cc ORDER BY roas DESC;

-- ROAs whose origin AS is registered in a different country than the prefix
SELECT prefix, origin_as, cc, origin_as_cc FROM roadata
WHERE cc <> origin_as_cc AND 'ZZ' NOT IN (cc, origin_as_cc);

-- When was each source fetched?
SELECT source, fetched_at_utc, source_serial, row_count FROM meta;
```

## Development

```sh
make test          # ruff check, ruff format --check, pytest (offline only)
uv run pytest -m network   # also checks that the live source URLs answer
```

Tests never touch the network unless asked to. Fixtures in `tests/fixtures/` are trimmed lines from real source files. See [CLAUDE.md](CLAUDE.md) for the code layout and conventions, and [PLAN.md](PLAN.md) for the rewrite history.

## License

BSD 2-Clause. See [LICENSE](LICENSE).
