#########################################################################################
'''
delegated.py: Implements delegated API on top of csv import
(c) carlos@lacnic.net 20151201
'''

from cm2c.csvimport.sql3load import sql3load
from cm2c.commons.gen.utils import get_tmp_fn
from cm2c.commons.gen.getfile import getfile
from cm2c.commons.debug.dprint import dprint
from lacniclabs.etc import rirconfig

## begin
class delegatedStats(object):
    '''
    Imports delegated stats file from the RIRs.
    '''

    dbh = 0
    '''
    dbh: sql3load database handle.
    '''

    # begin
    def __init__(self, **kwargs):
        self.drir  = kwargs.get('rir','lacnic')
        self.ddate = kwargs.get('date', 'latest')
        # get archivo delegated
        self._download_stats_file(rir=self.drir, date=self.ddate)

        ## load into database
        self.s3_template = [ ('name', 'text'), ('age', 'integer'), ('weigth', 'float') ]
        self.s3l = sql3load(self.s3_template, get_tmp_fn(".db") )
        r = self.s3l.importFile("test/test-import.txt")
        self.dbh = sql3load("")
        pass
    # end

    def _download_stats_file(self, **kwargs):
        """
        Downloads stats file for a given rir and date.
        Args 'rir' and 'date' (date can be 'latest')
        Load delegated-stats file and current RIR for given date (YYYYMMDD|latest)
        """
        dp = dprint()
        # get delegated
        ddate = kwargs.get('date', 'latest')
        drir  = kwargs.get('rir', 'lacnic')
        dp.log("Downloading stat file for RIR %s, date %s..." % (self.drir, self.ddate))
        dlg_tmpfile = get_tmp_fn("delegated-extended-%s-%s" % (drir, ddate))
        dlg_tmpfile = getfile(rirconfig.rir_config_data[self.drir]['dlge'][0] % (self.ddate), dlg_tmpfile,43200)
        pp.log(" OK\n")
    # end

## end

if __name__ == "__main__":
    print "Not to be run directly"

# END file
#########################################################################################
