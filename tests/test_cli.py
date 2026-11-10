from typer.testing import CliRunner

from rir_netdata import __version__
from rir_netdata.cli import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
