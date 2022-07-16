#!/usr/bin/env python3
"""
netdata3, top element of the project.
=============================================

:author: CarlosM
:date: July 2022



"""

# BEGIN
import click

_VERSION = "3.0.1"

@click.group()
def cli():
    pass

@click.command()
@click.option("--dataset", help="Dataset to import. Values are delegated|ris|rpki")
def load(dataset):
    print(f"Importing dataset: {dataset}")
# end import

cli.add_command(load)

if __name__ == "__main__":
    print("Bienvenido a netdada3")
    print(" ")
    print("(c) Carlos M. Martinez, julio 2022 @SanPedroDelTimote")
    print(f"Version: {_VERSION}")
    cli()

# END
