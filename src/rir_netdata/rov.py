"""RPKI route origin validation (RFC 6811) of ``riswhois`` routes against ``roadata``.

SPEC.md §4.5, issue #8. Fills ``riswhois.rovstatus``, ``rovreason`` and ``rov_roas``.

ROAs are indexed in memory by (address bits, prefix length, network as an int). For each route
we look up only the prefix lengths that actually occur among ROAs and are no longer than the
route's own, so a route costs a handful of dict lookups. Networks are full-width ints (IPv6 as
128-bit), never the /64-unit ``istart`` alone: ROAs and routes can be longer than /64.
"""

import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from ipaddress import ip_network

from rir_netdata.sources import Tick

VALID, INVALID, NOTFOUND = "valid", "invalid", "notfound"
BATCH = 50_000

# (bits, network int, prefix length)
Key = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class Verdict:
    status: str
    reason: str | None
    roas: int


def key(rtype: str, prefix: str, istart: int | None, pfxlen: int | None) -> Key | None:
    """Full-width network key for a roadata/riswhois row, or None if it isn't a valid prefix."""
    if rtype == "ipv4":
        return 32, istart, pfxlen
    if rtype != "ipv6":
        return None
    if istart and pfxlen <= 64:  # global unicast: istart is exact in /64 units
        return 128, istart << 64, pfxlen
    net = ip_network(prefix, strict=False)  # longer than /64, or outside 2000::/3
    return 128, int(net.network_address), net.prefixlen


class RoaIndex:
    def __init__(self) -> None:
        self._roas: dict[Key, list[tuple[int, int]]] = defaultdict(list)
        self._lengths: dict[int, list[int]] = {32: [], 128: []}

    def add(self, k: Key, asn: int, maxlen: int) -> None:
        self._roas[k].append((asn, maxlen))

    def freeze(self) -> None:
        """Record which prefix lengths occur; call once after the last ``add``."""
        lengths: dict[int, set[int]] = {32: set(), 128: set()}
        for bits, _, plen in self._roas:
            lengths[bits].add(plen)
        self._lengths = {bits: sorted(ls) for bits, ls in lengths.items()}

    def validate(self, k: Key, origin: str) -> Verdict:
        bits, net, plen = k
        # AS-sets like '{40179}' have no single origin ASN, so they never match (RFC 6811).
        asn = int(origin) if origin and origin.isdigit() else None
        roas, valid, length_hit = 0, False, False
        for length in self._lengths[bits]:
            if length > plen:
                break
            shift = bits - length
            for roa_asn, maxlen in self._roas.get((bits, net >> shift << shift, length), ()):
                roas += 1
                if roa_asn == asn and roa_asn != 0:  # RFC 7607: AS0 ROAs never match
                    if plen <= maxlen:
                        valid = True
                    else:
                        length_hit = True
        if roas == 0:
            return Verdict(NOTFOUND, None, 0)
        if valid:
            return Verdict(VALID, None, roas)
        if origin and origin.startswith("{"):
            reason = "as_set"
        elif length_hit:
            reason = "length"
        else:
            reason = "asn"
        return Verdict(INVALID, reason, roas)


def load_index(conn: sqlite3.Connection, tick: Tick | None = None) -> RoaIndex:
    idx = RoaIndex()
    rows = conn.execute(
        "SELECT type, prefix, istart, pfxlen, origin_as2, maxlen FROM roadata"
        " WHERE type IN ('ipv4', 'ipv6')"
    )
    n = 0
    for rtype, prefix, istart, pfxlen, asn, maxlen in rows:
        idx.add(key(rtype, prefix, istart, pfxlen), int(asn), int(maxlen))
        n += 1
        if tick and n % BATCH == 0:
            tick(BATCH)
    if tick:
        tick(n % BATCH)
    idx.freeze()
    return idx


def count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def run(conn: sqlite3.Connection, idx: RoaIndex, tick: Tick | None = None) -> Counter[str]:
    """Validate every riswhois route against ``idx``; return the number of routes per status."""
    stats: Counter[str] = Counter()
    lo, hi = conn.execute("SELECT min(id), max(id) FROM riswhois").fetchone()
    if lo is None:
        return stats
    for start in range(lo, hi + 1, BATCH):
        rows = conn.execute(
            "SELECT id, type, prefix, istart, pfxlen, origin_as FROM riswhois"
            " WHERE id BETWEEN ? AND ?",
            (start, start + BATCH - 1),
        ).fetchall()
        updates = []
        for rid, rtype, prefix, istart, pfxlen, origin in rows:
            k = key(rtype, prefix, istart, pfxlen)
            if k is None:
                continue  # unparseable prefix: columns stay NULL
            v = idx.validate(k, origin)
            stats[v.status] += 1
            updates.append((v.status, v.reason, v.roas, rid))
        conn.executemany(
            "UPDATE riswhois SET rovstatus = ?, rovreason = ?, rov_roas = ? WHERE id = ?",
            updates,
        )
        if tick:
            tick(len(rows))
    return stats
