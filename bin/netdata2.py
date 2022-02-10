#!/usr/bin/env python
"""
Generates daily delegated db dump for lacnic

:author: Carlos M. Martinez, carlos@lacnic.net
:date: 20151228
:date: 20160523
:date: 20170224 - fixed import roa data
:date: 20170404 - forked from genDailyDlgDB, added click cmd line framework
:date: 20180308 - fixed use of date parameter for delegated import

./netdata --dset=[delegated|ripevalapp|riswhois|all] --rir=[<rir name>|all] --date=[YYYYMMDD|latest] \
          --basename=[var/netdata]

"""

import click
import sys
import lacniclabs.netdata.delegated as dlg
import lacniclabs.netdata.riswhois as rwh
import lacniclabs.netdata.riperpki as rpki # import ripevalRoaData
from datetime import date

# program version
prg_version = "0.1.2"
prg_date = "2018-03-08"

# set filename
fname_base = "%s-%s.db" % ("var/netdata",date.today())
dateToday = date.today()


def import_delegated_stats(rir, w_date):
    ## Import delegated stats files
    print "====>> RUNNING: Import delegated stats files"
    if rir == "lacnic" or rir == "all":
        d = dlg.delegatedStats(rir='lacnic', date=w_date, db_filename=fname_base)
    if rir == "arin" or rir == "all":
        d = dlg.delegatedStats(rir='arin', date=w_date, db_filename=fname_base, as_cache=True)
    if rir == "ripencc" or rir == "all":
        d = dlg.delegatedStats(rir='ripencc', date=w_date, db_filename=fname_base, as_cache=True)
    if rir == "afrinic" or rir == "all":
        d = dlg.delegatedStats(rir='afrinic', date=w_date, db_filename=fname_base, as_cache=True)
    if rir == "apnic" or rir == "all":
        d = dlg.delegatedStats(rir='apnic', date=w_date, db_filename=fname_base, as_cache=True)
    print " "
    print "============================================="
## END import delegated stats


def import_riswhois(rir, date):
    ## Import RISWHOIS
    print "====>> RUNNING: Import RISWHOIS origin AS stats"
    r = rwh.risWhois(date='latest', db_filename=fname_base)
    print " "
    print "============================================="
# END import riswhois


def import_ripevalapp(rir, date):
    ## Import ROADATA
    print "====>> RUNNING: Import RPKI validator ROA data"
    k = rpki.ripevalRoaData(db_filename=fname_base, url="https://ripeval.labs.lacnic.net/api/export.csv")
    print " "
    print "============================================="
## END import_rpkivalapp():


@click.group()
@click.option("--verbose", default=False, help="Verbose messages")
def cli(verbose):
    click.echo("Verbose messaging set to %s" % verbose)
    pass

@cli.command()
@click.option("--rir", default="all", help="RIR data to import, can be all|<rirname>. Defaults to all")
@click.option("--date", default="latest", help="Date to import in YYYYMMDD format or 'latest'. Defaults to 'latest'")
@click.option("--dset", default="all", help="Dataset to import, can be delegated|ripevalapp|riswhois|all. Defaults to all")
@click.option("--basename", default="var/netdata", help="Filename base, defaults to var/netdata. Date tag is added automatically")
def get(rir, date, dset, basename):
    global fname_base, dateToday
    # dateToday = date.today()
    if date == "latest":
        fname_base = "%s-%s.db" % (basename, dateToday.strftime("%Y%m%d") )
    else:
        fname_base = "%s-%s.db" % (basename, date)
    click.echo("Database filename is %s" % (fname_base))

    # print "date %s" % (date)
    # sys.exit(-1)

    if dset=="delegated" or dset=="all":
        import_delegated_stats(rir, date)

    if dset == "ripevalapp" or dset == "all":
        import_ripevalapp(rir, date)

    if dset == "riswhois" or dset == "all":
        import_riswhois(rir, date)

    # if dset not in ['']
## END import tasks

@cli.command()
def cleanup():
    click.echo("Doing some cleanup... WARN: TBI (right now it does nothing)\n")
    pass
## END cleanup


if __name__ == "__main__":
    #
    click.echo("Welcome to NETDATA: Importing Internet addressing-related datasets\n")
    click.echo("   Author : carlos@lacnic.net")
    click.echo("   Version: %s, released %s\n" % (prg_version, prg_date))
    cli()
    sys.exit()
