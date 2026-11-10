from pathlib import Path

import pytest

from rir_netdata import config


def test_defaults_cover_every_rir():
    cfg = config.load()
    assert set(cfg.delegated) == set(config.RIRS)
    assert all(u.startswith("https://") for u in cfg.delegated.values())
    assert cfg.freshness_seconds.riswhois == 86400


def test_override_is_layered(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text(
        'cache_dir = "/var/cache/netdata"\n'
        "[retry]\nattempts = 2\n"
        '[sources.delegated]\nlacnic = "https://mirror.example/lacnic"\n'
    )
    cfg = config.load(f)
    assert cfg.cache_dir == Path("/var/cache/netdata")
    assert cfg.retry == config.Retry(attempts=2, max_wait_seconds=60.0)
    assert cfg.delegated["lacnic"] == "https://mirror.example/lacnic"
    assert cfg.delegated["arin"] == config.DEFAULT_DELEGATED["arin"]
    assert cfg.rpki == config.DEFAULT_RPKI


@pytest.mark.parametrize(
    "body",
    [
        "typo = 1\n",
        "[retry]\nattemps = 2\n",
        '[sources.delegated]\nlacnik = "x"\n',
        "[sources.bgp]\n",
    ],
)
def test_unknown_keys_rejected(tmp_path, body):
    f = tmp_path / "c.toml"
    f.write_text(body)
    with pytest.raises(config.ConfigError, match="unknown key"):
        config.load(f)


def test_bad_toml(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text("not = = toml")
    with pytest.raises(config.ConfigError):
        config.load(f)
