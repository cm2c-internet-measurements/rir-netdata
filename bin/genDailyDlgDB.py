"""
Generates daily delegated db dump for lacnic

:author: Carlos M. Martinez, carlos@lacnic.net
:date: 20151228
:date: 20160523

"""

import sys
import lacniclabs.netdata.delegated as dlg
import lacniclabs.netdata.riswhois as rwh

## Import delegated stats files
d = dlg.delegatedStats(rir='lacnic', date='latest', db_filename='var/netdata-latest.db')
d = dlg.delegatedStats(rir='arin', date='latest', db_filename='var/netdata-latest.db', as_cache=True)
d = dlg.delegatedStats(rir='ripencc', date='latest', db_filename='var/netdata-latest.db', as_cache=True)
d = dlg.delegatedStats(rir='afrinic', date='latest', db_filename='var/netdata-latest.db', as_cache=True)
d = dlg.delegatedStats(rir='apnic', date='latest', db_filename='var/netdata-latest.db', as_cache=True)

## Import RISWHOIS
r = rwh.risWhois(date='latest', db_filename='var/netdata-latest.db')

sys.exit()
