"""Command-line interface."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from rir_netdata import __version__, config, pipeline

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
console = Console(stderr=True)

RirChoice = StrEnum("RirChoice", {name: name for name in ("all", *config.RIRS)})


def _version(value: bool) -> None:
    if value:
        console.print(f"rir-netdata [bold]{__version__}[/]")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version, is_eager=True, help="Show version and exit."),
    ] = False,
) -> None:
    """Build a daily SQLite snapshot of Internet number-resource datasets."""


@app.command()
def get(
    source: Annotated[
        pipeline.Source, typer.Option(help="Dataset to import.")
    ] = pipeline.Source.all,
    rir: Annotated[RirChoice, typer.Option(help="Delegated file(s) to import.")] = "all",
    output_dir: Annotated[Path, typer.Option(help="Directory for the output db.")] = Path("var"),
    basename: Annotated[
        str, typer.Option(help="Output filename prefix; date is appended.")
    ] = "netdata",
    config_file: Annotated[
        Path | None, typer.Option("--config", help="TOML config overrides.")
    ] = None,
) -> None:
    """Download sources and build the snapshot database."""
    try:
        cfg = config.load(config_file)
    except config.ConfigError as e:
        console.print(f"[red]error:[/] {e}")
        raise typer.Exit(2) from e

    rirs = list(config.RIRS) if rir == "all" else [rir.value]
    target = pipeline.output_path(output_dir, basename, datetime.now(UTC))
    console.print(f"[bold]rir-netdata {__version__}[/] → {target}")
    try:
        pipeline.run(cfg, source, rirs, target, console)
    except Exception as e:
        console.print(f"[red bold]run failed, no database written:[/] {type(e).__name__}: {e}")
        raise typer.Exit(1) from e
