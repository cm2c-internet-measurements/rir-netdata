"""
Generates daily delegated db dump for lacnic

:author: Carlos M. Martinez, carlos@lacnic.net
:date: 20151228

"""

import sys
import lacniclabs.netdata.delegated as dlg

d = dlg.delegatedStats(rir='lacnic', date='latest', db_filename='var/dlglacnic-latest.db')

sys.exit()
