import pytest

from rir_netdata.addr import Resource, from_delegated, from_prefix

INT64_MAX = 2**63 - 1


class TestDelegatedIPv4:
    def test_cidr_aligned(self):
        r = from_delegated("ipv4", "200.0.0.0", 65536)
        assert r == Resource("ipv4", 3355443200, 3355508735, 16, "200.0.0.0/16", 256)

    def test_non_power_of_two_is_range(self):
        r = from_delegated("ipv4", "192.0.2.0", 768)
        assert r.iend == r.istart + 767
        assert r.prefix == "192.0.2.0-192.0.4.255"
        assert r.pfxlen is None
        assert r.equiv == 3

    def test_power_of_two_but_unaligned_is_range(self):
        r = from_delegated("ipv4", "10.0.1.0", 512)
        assert r.prefix == "10.0.1.0-10.0.2.255"
        assert r.pfxlen is None

    def test_sub_24_equiv_floors_to_zero(self):
        assert from_delegated("ipv4", "10.0.0.0", 128).equiv == 0

    def test_single_24(self):
        r = from_delegated("ipv4", "10.0.0.0", 256)
        assert (r.prefix, r.equiv, r.iend - r.istart) == ("10.0.0.0/24", 1, 255)


class TestDelegatedIPv6:
    def test_slash32(self):
        r = from_delegated("ipv6", "2001:db8::", 32)
        assert r.istart == 0x20010DB800000000
        assert r.iend == 0x20010DB8FFFFFFFF
        assert (r.prefix, r.pfxlen, r.equiv) == ("2001:db8::/32", 32, 1)

    def test_slash48_equiv_floors_to_zero(self):
        r = from_delegated("ipv6", "2001:db8:1::", 48)
        assert r.iend - r.istart + 1 == 2**16
        assert r.equiv == 0

    def test_slash20(self):
        assert from_delegated("ipv6", "2800::", 20).equiv == 2**12


class TestDelegatedASN:
    def test_inclusive_end(self):
        r = from_delegated("asn", "28000", 1)
        assert (r.istart, r.iend, r.prefix, r.equiv) == (28000, 28000, "na/asn", 1)

    def test_block(self):
        r = from_delegated("asn", "64512", 1024)
        assert (r.istart, r.iend, r.equiv) == (64512, 65535, 1024)


def test_summary_block_returns_none():
    assert from_delegated("ipv4", "*", 1000) is None


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        from_delegated("ipv5", "1.2.3.4", 1)


class TestPrefix:
    def test_ipv4(self):
        r = from_prefix("200.7.84.0/23")
        assert r == Resource("ipv4", 3355923456, 3355923967, 23, "200.7.84.0/23", 2)

    def test_ipv4_sub_24(self):
        assert from_prefix("200.7.84.0/25").equiv == 0

    def test_ipv4_host_bits_tolerated(self):
        r = from_prefix("10.0.0.1/24")
        assert r.istart == from_prefix("10.0.0.0/24").istart

    def test_ipv6(self):
        r = from_prefix("2001:13c7:7000::/36")
        assert (r.type, r.pfxlen, r.equiv) == ("ipv6", 36, 0)
        assert r.istart == 0x200113C770000000
        assert r.iend == 0x200113C77FFFFFFF

    def test_ipv6_outside_global_unicast_keeps_pfxlen(self):
        assert from_prefix("fc00::/7") == Resource("ipv6", 0, 0, 7, "fc00::/7", 0)

    @pytest.mark.parametrize(
        ("pfx", "kind"),
        [("IP Prefix", "badipv4"), ("300.0.0.0/8", "badipv4"), ("2001:zz::/32", "badipv6")],
    )
    def test_bad(self, pfx, kind):
        assert from_prefix(pfx) == Resource(kind, -1, -1, -1, pfx, 0)

    @pytest.mark.parametrize("pfx", ["", None])
    def test_empty(self, pfx):
        assert from_prefix(pfx).type == "na"


@pytest.mark.parametrize(
    "r",
    [
        from_prefix("255.255.255.255/32"),
        from_prefix("3fff:ffff:ffff:ffff::/64"),
        from_prefix("ffff::/16"),
        from_delegated("asn", "4294967295", 1),
    ],
)
def test_fits_int64(r):
    assert r.iend <= INT64_MAX
