"""Cross-check riswhois ROV columns against a Routinator instance's validity API.

Usage: uv run python scripts/rov_crosscheck.py var/netdata-YYYYMMDD.db [--per-status 400]

Draws a random sample of routes per rovstatus (AS-set origins excluded, since the API needs a
single ASN), asks Routinator for each, and reports agreement on status, reason and the number
of covering ROAs. Hits the network; it's a manual tool, not part of the test suite.

Routinator calls a route "length"-invalid when none of its covering VRPs fails on ASN alone;
SPEC §4.5 only says `length` when a covering ROA has the route's own ASN. Reasons are therefore
compared with SPEC's definition, applied to the VRPs Routinator returns.
"""

import argparse
import json
import random
import sqlite3
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

STATE = {"valid": "valid", "invalid": "invalid", "not-found": "notfound"}


def ask(api: str, origin: str, prefix: str) -> dict:
    url = f"{api}/api/v1/validity/AS{origin}/{prefix}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)["validated_route"]["validity"]
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2)
    raise AssertionError("unreachable")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("db")
    ap.add_argument("--per-status", type=int, default=400)
    ap.add_argument("--api", default="https://routinator.labs.lacnic.net")
    ap.add_argument("--seed", type=int, default=8)
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    random.seed(args.seed)
    sample = []
    for status in STATE.values():
        rows = conn.execute(
            "SELECT origin_as, prefix, rovstatus, rovreason, rov_roas FROM riswhois"
            " WHERE rovstatus = ? AND origin_as NOT LIKE '{%'",
            (status,),
        ).fetchall()
        sample += random.sample(rows, min(args.per_status, len(rows)))

    def check(row):
        origin, prefix, *_ = row
        return row, ask(args.api, origin, prefix)

    tally: Counter[str] = Counter()
    diffs = []
    with ThreadPoolExecutor(6) as ex:
        for (origin, prefix, status, reason, roas), v in ex.map(check, sample):
            vrps = v["VRPs"]
            api_status = STATE[v["state"]]
            api_reason = None
            if api_status == "invalid":
                own_asn = any(x["asn"] == f"AS{origin}" for x in vrps["unmatched_length"])
                api_reason = "length" if own_asn else "asn"
            api_roas = len(
                {(x["asn"], x["prefix"], x["max_length"]) for k in vrps for x in vrps[k]}
            )
            ok = (api_status, api_reason, api_roas) == (status, reason, roas)
            tally["agree" if ok else "differ"] += 1
            if not ok:
                diffs.append(
                    (origin, prefix, (status, reason, roas), (api_status, api_reason, api_roas))
                )

    print(f"{len(sample)} routes: {dict(tally)}")
    for d in diffs[:20]:
        print("  ", d)


if __name__ == "__main__":
    main()
