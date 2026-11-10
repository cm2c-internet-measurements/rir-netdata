"""Command-line interface."""

import typer
from rich.console import Console

from rir_netdata import __version__

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
console = Console(stderr=True)


def _version(value: bool) -> None:
    if value:
        console.print(f"rir-netdata [bold]{__version__}[/]")
        raise typer.Exit


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Show version and exit."
    ),
) -> None:
    """Build a daily SQLite snapshot of Internet number-resource datasets."""


@app.command()
def get() -> None:
    """Download all sources and build the snapshot database."""
    console.print("[yellow]not implemented yet[/]")
    raise typer.Exit(1)
