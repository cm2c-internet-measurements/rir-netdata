#!/usr/bin/env python
# ----------------------------------------------------------------
# SIMPLEWHOIS: (c) carlos@lacnic.net 20180313
#
# v0.1: Simple queries via command line
# ----------------------------------------------------------------

import unittest
import sqlite3
import click
import sys

from SimpleWhois.SimpleWhois import SimpleWhois

_VERSION = "0.1"
_AUTHOR = "carlos@lacnic.net"

@click.group()
def cli():
    pass

@cli.command()
@click.option('--query', help='AS number')
def autnum(query):
    global sw
    click.echo("AUTNUM query: %s" % (query) )
    r = sw.autnum(query)
    click.echo(" R: %s" % ( dict(r) ) )
## end autnum

@cli.command()
@click.option('--query', help='AS number')
def ip(query):
    click.echo("IP query: %s" % (query) )
## end ip

@cli.command()
@click.option('--fields', default='cc', help="List of fields to include, separated by commas")
@click.option('--outfile', default='-', help="Output file name, use - for stdout")
def bulk_query(fields, outfile):
    """
    Read a list of ASNs or IP resources from STDIN and return SimpleWhois info on STDOUT.
    """
    global sw

    f = None
    if outfile == "-":
        f = sys.stdout
    else:
        f = open(outfile, "w")

    for line in sys.stdin:
        line = line.strip()
        if line.find("#") != 0: #if comment, skip
            parts = line.split("|")
            f.write(parts)
            r = sw.autnum(parts[0].strip())
            if r != None:
                f.write("%s | %s\n" % (line, r[fields]))
            else:
                f.write("%s | %s\n" % (line, None) )

    if outfile != "-":
        f.close()
## end bulk query

if __name__ == "__main__":
    sw = SimpleWhois("var/netdata-2018-03-07.db")
    click.echo( "SimpleWhois: %s, (c) %s\n" % (_VERSION, _AUTHOR) )
    cli()
    sys.exit()

## end simple whois
