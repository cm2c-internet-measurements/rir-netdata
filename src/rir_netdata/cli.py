"""Command-line interface."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from rir_netdata import __version__, config, export, pipeline

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
    export_formats: Annotated[
        list[str] | None,
        typer.Option(
            "--export",
            help="Also export to these formats (comma-separated or repeated): "
            + ", ".join(f.value for f in export.Format)
            + ". Written to <output-dir>/<basename>-YYYYMMDD/; sqlite.gz goes next to the db.",
        ),
    ] = None,
) -> None:
    """Download sources and build the snapshot database."""
    try:
        cfg = config.load(config_file)
        formats = export.parse_formats(export_formats or [])
    except (config.ConfigError, export.ExportError) as e:
        console.print(f"[red]error:[/] {e}")
        raise typer.Exit(2) from e

    rirs = list(config.RIRS) if rir == "all" else [rir.value]
    target = pipeline.output_path(output_dir, basename, datetime.now(UTC))
    console.print(f"[bold]rir-netdata {__version__}[/] → {target}")
    try:
        pipeline.run(cfg, source, rirs, target, console, formats)
    except Exception as e:
        console.print(f"[red bold]run failed, no database written:[/] {type(e).__name__}: {e}")
        raise typer.Exit(1) from e


@app.command(name="export")
def export_cmd(
    database: Annotated[Path, typer.Argument(help="An existing netdata .db (v2 or legacy).")],
    formats_arg: Annotated[
        list[str],
        typer.Option(
            "--format",
            help="Formats (comma-separated or repeated): "
            + ", ".join(f.value for f in export.Format),
        ),
    ],
    output_dir: Annotated[
        Path | None,
        typer.Option(
            help="Where the export directory (and the .db.gz) go. Default: next to the database."
        ),
    ] = None,
) -> None:
    """Export an existing database to other formats."""
    try:
        formats = export.parse_formats(formats_arg)
    except export.ExportError as e:
        console.print(f"[red]error:[/] {e}")
        raise typer.Exit(2) from e
    if not formats:
        console.print("[red]error:[/] no export format given")
        raise typer.Exit(2)
    if not database.is_file():
        console.print(f"[red]error:[/] no such database: {database}")
        raise typer.Exit(2)

    final = (output_dir or database.parent) / database.stem
    console.print(f"[bold]rir-netdata {__version__}[/] export {database} → {final}/")
    stage = export.Stage(final)
    try:
        with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as conn:
            pipeline.write_exports(conn, formats, stage, console)
        published = pipeline.publish_exports(formats, database, stage, console)
    except Exception as e:
        stage.discard()
        console.print(f"[red bold]export failed, nothing written:[/] {type(e).__name__}: {e}")
        raise typer.Exit(1) from e
    pipeline.print_exports(console, stage, published)
