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
import math
import ipaddr

## begin
class delegatedStats(object):
    '''
    Imports delegated stats file from the RIRs.

    Class attributes:
        s3l / dbh : handle to sql3load instance.
    '''

    #dbh = None
    #'''
    #dbh: sql3load database handle.
    #'''

    # begin
    def __init__(self, **kwargs):
        """
        Class constructor, receives keyword arguments {rir} and {date}
        """
        self.drir  = kwargs.get('rir','lacnic')
        self.ddate = kwargs.get('date', 'latest')
        self.local_file = kwargs.get('local_file', None)

        # get archivo delegated
        if self.local_file == None:
            self.dlg_fn_name = self._download_stats_file(rir=self.drir, date=self.ddate)
        else:
            self.dlg_fn_name = self.local_file

        ## load into database
        self.s3_template = [ ('rir', 'text'), ('cc', 'text'), ('type', 'text'),
                             ('block', 'text'), ('length', 'integer'), ('date', 'integer'),
                             ('status', 'text'), ('orgid', 'integer')
                            ]
        self.s3l = sql3load(self.s3_template, get_tmp_fn(".db"), "numres" )
        # print self.dlg_fn_name
        r = self.s3l.importFile(self.dlg_fn_name, "|")
        # self.dbh = sql3load("")
        self.dbh = self.s3l
        pass
    # end

    # begin
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
        dlg_tmpfile = get_tmp_fn(filename="delegated-extended-%s-%s" % (drir, ddate) )
        dlg_tmpfile_name = getfile(rirconfig.rir_config_data[self.drir]['dlge'][0] % (self.ddate), dlg_tmpfile,43200)
        dp.log(" OK\n")
        return dlg_tmpfile_name
    # end

    # begin
    def _add_numeric_columns(self):
        r1 = self.dbh.addMetaColumn("istart INTEGER")
        r2 = self.dbh.addMetaColumn("iend INTEGER")
        return r1 and r2
    #end

    # begin
    def _add_prefix_column(self):
        r = self.dbh.addMetaColumn("prefix VARCHAR(80)")
        p = self.dbh.calculateMetaColumn("prefix", self._populate_prefix_column)
        return r
    # end
    #begin
    #@staticmethod
    def _populate_prefix_column(self,w_row):
        if w_row['type'] == 'ipv4' and w_row['block'] != '*':
            pfx_len = 32 - int( math.log( int(w_row['length']), 2) )
            pfx = ipaddr.IPv4Network(w_row['block'] + "/" + str(pfx_len))
            #w_row['prefix'] = str(pfx)
            #w_row['istart'] = int(pfx.network)
            #w_row['iend'] = int(pfx.broadcast)
            #w_row['equiv'] = (w_row['iend']-w_row['istart'])/256 + 1
            return str(pfx)
        elif w_row['type'] == 'ipv6' and w_row['block'] != '*':
            pfx_norm_base = pow(2,64)
            #print "row %s" % (dict(w_row))
            pfx = ipaddr.IPv6Network( w_row['block'] + "/" +  str(w_row['length']) )
            #w_row['prefix'] = str(pfx)
            #w_row['istart'] = int(pfx.network) / pfx_norm_base
            #w_row['iend'] = int(pfx.broadcast) / pfx_norm_base
            #w_row['equiv'] = (w_row['iend'] - w_row['istart'] + 1) / pow(2,32)
            return str(pfx)
        else:
            #w_row['prefix'] = 'na/asn'
            #w_row['istart'] = int(w_row['start'])
            #w_row['iend'] = int(w_row['start']) + int(w_row['value'])
            #w_row['equiv'] = 'na'
            return 'na/asn'
    #end

    # begin
    def _add_equiv_column(self):
        r = self.dbh.addMetaColumn("equiv INTEGER")
        return r
    # end

## end

if __name__ == "__main__":
    print "Not to be run directly"

# END file
#########################################################################################
