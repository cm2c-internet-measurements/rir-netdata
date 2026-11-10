"""Address math shared by every source.

Turns a delegated (type, block, length) triple or a textual prefix into the derived columns
defined in SPEC.md §4-5: type, istart, iend, pfxlen, prefix and equiv.

Units (SPEC §5.5): IPv4 in addresses, IPv6 in /64s (address >> 64), ASNs as ASNs.
Ranges are inclusive. ``equiv`` is an integer floor of /24s (IPv4) or /32s (IPv6).
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
    equiv: int | None


def _is_pow2(n: int) -> bool:
    return n > 0 and n & (n - 1) == 0


def _ipv6(net: IPv6Network) -> Resource:
    if not net.subnet_of(GLOBAL_UNICAST):
        return Resource("ipv6", 0, 0, net.prefixlen, str(net), 0)
    istart = int(net.network_address) >> 64
    iend = int(net.broadcast_address) >> 64
    return Resource(
        "ipv6", istart, iend, net.prefixlen, str(net), (iend - istart + 1) // V6_EQUIV_UNIT
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
        return Resource("ipv4", istart, iend, pfxlen, prefix, length // V4_EQUIV_UNIT)
    if rtype == "ipv6":
        return _ipv6(IPv6Network(f"{block}/{length}", strict=False))
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
            return _ipv6(IPv6Network(pfx, strict=False))
        net = IPv4Network(pfx, strict=False)
    except (AddressValueError, NetmaskValueError, ValueError):
        return Resource(f"bad{family}", -1, -1, -1, pfx, 0)
    return Resource(
        "ipv4",
        int(net.network_address),
        int(net.broadcast_address),
        net.prefixlen,
        pfx,
        net.num_addresses // V4_EQUIV_UNIT,
    )
