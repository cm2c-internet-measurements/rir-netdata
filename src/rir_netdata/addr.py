"""Address math shared by every source.

Turns a delegated (type, block, length) triple or a textual prefix into the derived columns
defined in SPEC.md §4-5: type, istart, iend, pfxlen, prefix, equiv and equiv2.

Units (SPEC §5.5): IPv4 in addresses, IPv6 in /64s (address >> 64), ASNs as ASNs.
Ranges are inclusive. ``equiv`` reproduces the legacy formula of each table exactly, for
compatibility with existing scripts (SPEC §5.6); ``equiv2`` is the exact integer size.
"""

from dataclasses import dataclass
from ipaddress import AddressValueError, IPv4Address, IPv4Network, IPv6Network, NetmaskValueError

# Only global unicast is mapped to /64 units; anything else would overflow SQLite's int64.
GLOBAL_UNICAST = IPv6Network("2000::/3")

V4_EQUIV_UNIT = 2**8  # addresses per /24
V6_EQUIV_UNIT = 2**32  # /64s per /32


@dataclass(frozen=True, slots=True)
class Resource:
    type: str
    istart: int | None
    iend: int | None
    pfxlen: int | None
    prefix: str | None
    equiv: int | float | None
    equiv2: int | None = None  # roadata only: /24s (IPv4) or whole /64s (IPv6)


def _is_pow2(n: int) -> bool:
    return n > 0 and n & (n - 1) == 0


def _ipv6(net: IPv6Network, *, fractional: bool) -> Resource:
    """``fractional`` selects the roadata equiv (float /32s) over the numres one (floor)."""
    plen = net.prefixlen
    if not net.subnet_of(GLOBAL_UNICAST):
        return Resource("ipv6", 0, 0, plen, str(net), 0, 0 if fractional else None)
    istart = int(net.network_address) >> 64
    iend = int(net.broadcast_address) >> 64
    if not fractional:
        return Resource("ipv6", istart, iend, plen, str(net), (iend - istart + 1) // V6_EQUIV_UNIT)
    # Legacy formula, kept verbatim: anything longer than a /64 counts as one /64 here.
    equiv = (iend - istart + 1) / V6_EQUIV_UNIT
    return Resource(
        "ipv6", istart, iend, plen, str(net), equiv, 2 ** (64 - plen) if plen <= 64 else 0
    )


def from_delegated(rtype: str, block: str, length: int) -> Resource | None:
    """Derive columns for a delegated-extended record. Returns None for '*' (summary) blocks."""
    if block == "*":
        return None
    if rtype == "ipv4":
        istart = int(IPv4Address(block))
        iend = istart + length - 1
        if _is_pow2(length) and istart % length == 0:
            pfxlen = 32 - (length.bit_length() - 1)
            prefix = f"{block}/{pfxlen}"
        else:
            pfxlen = None
            prefix = f"{block}-{IPv4Address(iend)}"
        # Legacy numres formula: any partial /24 counts as one.
        return Resource("ipv4", istart, iend, pfxlen, prefix, (iend - istart) // V4_EQUIV_UNIT + 1)
    if rtype == "ipv6":
        return _ipv6(IPv6Network(f"{block}/{length}", strict=False), fractional=False)
    if rtype == "asn":
        istart = int(block)
        return Resource("asn", istart, istart + length - 1, None, "na/asn", length)
    raise ValueError(f"unknown resource type {rtype!r}")


def from_prefix(pfx: str | None) -> Resource:
    """Derive columns for a CIDR prefix (ROA or RIS entry). Bad prefixes map to badipv4/badipv6."""
    if not pfx:
        return Resource("na", None, None, None, pfx, None)
    family = "ipv6" if ":" in pfx else "ipv4"
    try:
        if family == "ipv6":
            return _ipv6(IPv6Network(pfx, strict=False), fractional=True)
        net = IPv4Network(pfx, strict=False)
    except (AddressValueError, NetmaskValueError, ValueError):
        return Resource(f"bad{family}", -1, -1, -1, pfx, 0, 0)
    slash24s = net.num_addresses // V4_EQUIV_UNIT
    return Resource(
        "ipv4",
        int(net.network_address),
        int(net.broadcast_address),
        net.prefixlen,
        pfx,
        slash24s,
        slash24s,
    )
