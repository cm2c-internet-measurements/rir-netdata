"""
Generates daily delegated db dump for lacnic

:author: Carlos M. Martinez, carlos@lacnic.net
:date: 20151228
:date: 20160523
:date: 20170224 - fixed import roa data
:date: 20170404 - forked from genDailyDlgDB, added click cmd line framework

"""

import click
import sys
import lacniclabs.netdata.delegated as dlg
import lacniclabs.netdata.riswhois as rwh
import lacniclabs.netdata.riperpki as rpki # import ripevalRoaData
from datetime import date

# set filename
fname_base = "var/netdata-%s.db" % (date.today())

## Import delegated stats files
print "====>> RUNNING: Import delegated stats files"
d = dlg.delegatedStats(rir='lacnic', date='latest', db_filename=fname_base)
d = dlg.delegatedStats(rir='arin', date='latest', db_filename=fname_base, as_cache=True)
d = dlg.delegatedStats(rir='ripencc', date='latest', db_filename=fname_base, as_cache=True)
d = dlg.delegatedStats(rir='afrinic', date='latest', db_filename=fname_base, as_cache=True)
d = dlg.delegatedStats(rir='apnic', date='latest', db_filename=fname_base, as_cache=True)
print " "
print "============================================="

## Import RISWHOIS
print "====>> RUNNING: Import RISWHOIS origin AS stats"
r = rwh.risWhois(date='latest', db_filename=fname_base)
print " "
print "============================================="


## Import ROADATA
print "====>> RUNNING: Import RPKI validator ROA data"
k = rpki.ripevalRoaData(db_filename=fname_base)
print " "
print "============================================="


sys.exit()
