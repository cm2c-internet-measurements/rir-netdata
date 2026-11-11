"""Runtime configuration: built-in defaults, optionally overridden by a TOML file.

Example override file (every key is optional)::

    cache_dir = "tmp"

    [retry]
    attempts = 5
    max_wait_seconds = 60

    [freshness_seconds]
    delegated = 3600

    [sources.delegated]
    lacnic = "https://mirror.example.net/delegated-lacnic-extended-latest"

    [sources.rpki]
    url = "https://rpki.example.net/json"

    [sources.riswhois]
    ipv4 = "https://www.ris.ripe.net/dumps/riswhoisdump.IPv4.gz"
"""

import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

RIRS = ("lacnic", "arin", "ripencc", "afrinic", "apnic")

DEFAULT_DELEGATED = {
    "lacnic": "https://ftp.lacnic.net/pub/stats/lacnic/delegated-lacnic-extended-latest",
    "arin": "https://ftp.arin.net/pub/stats/arin/delegated-arin-extended-latest",
    "ripencc": "https://ftp.ripe.net/pub/stats/ripencc/delegated-ripencc-extended-latest",
    "afrinic": "https://ftp.afrinic.net/pub/stats/afrinic/delegated-afrinic-extended-latest",
    "apnic": "https://ftp.apnic.net/stats/apnic/delegated-apnic-extended-latest",
}
DEFAULT_RPKI = {"url": "https://routinator.labs.lacnic.net/json"}  # Routinator JSON
DEFAULT_RISWHOIS = {
    "ipv4": "https://www.ris.ripe.net/dumps/riswhoisdump.IPv4.gz",
    "ipv6": "https://www.ris.ripe.net/dumps/riswhoisdump.IPv6.gz",
}


@dataclass(frozen=True)
class Retry:
    attempts: int = 5
    max_wait_seconds: float = 60.0


@dataclass(frozen=True)
class Freshness:
    """How long a cached download is reused before fetching again (legacy values)."""

    delegated: int = 3600
    rpki: int = 3600
    riswhois: int = 86400


@dataclass(frozen=True)
class Config:
    cache_dir: Path = Path("tmp")
    retry: Retry = field(default_factory=Retry)
    freshness_seconds: Freshness = field(default_factory=Freshness)
    delegated: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_DELEGATED))
    rpki: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_RPKI))
    riswhois: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_RISWHOIS))


class ConfigError(ValueError):
    pass


def _check_keys(section: str, given: dict[str, Any], allowed: set[str]) -> None:
    if unknown := set(given) - allowed:
        raise ConfigError(f"unknown key(s) in [{section}]: {', '.join(sorted(unknown))}")


def _merge_dataclass(section: str, base: Any, given: dict[str, Any]) -> Any:
    _check_keys(section, given, {f.name for f in fields(base)})
    return replace(base, **given)


def _merge_urls(section: str, base: dict[str, str], given: dict[str, Any]) -> dict[str, str]:
    _check_keys(section, given, set(base))
    return base | given


def load(path: Path | None = None) -> Config:
    """Return the defaults, with values from the TOML file at ``path`` (if any) layered on top."""
    cfg = Config()
    if path is None:
        return cfg
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"cannot read config {path}: {e}") from e

    _check_keys("top level", data, {"cache_dir", "retry", "freshness_seconds", "sources"})
    sources = data.get("sources", {})
    _check_keys("sources", sources, {"delegated", "rpki", "riswhois"})
    return Config(
        cache_dir=Path(data.get("cache_dir", cfg.cache_dir)),
        retry=_merge_dataclass("retry", cfg.retry, data.get("retry", {})),
        freshness_seconds=_merge_dataclass(
            "freshness_seconds", cfg.freshness_seconds, data.get("freshness_seconds", {})
        ),
        delegated=_merge_urls("sources.delegated", cfg.delegated, sources.get("delegated", {})),
        rpki=_merge_urls("sources.rpki", cfg.rpki, sources.get("rpki", {})),
        riswhois=_merge_urls("sources.riswhois", cfg.riswhois, sources.get("riswhois", {})),
    )
