"""
delegated.py: Implements delegated API on top of csv import
(c) carlos@lacnic.net 20151201

:author: Carlos Martinez, carlos@lacnic.net
:date: 20151201

"""

#########################################################################################

from cm2c.csvimport.sql3load import sql3load
from cm2c.commons.gen.utils import get_tmp_fn
from cm2c.commons.gen.getfile import getfile
from cm2c.commons.debug.dprint import dprint
from lacniclabs.etc import rirconfig
import math
import ipaddr
import sys
import os

## begin
class delegatedStats(object):
    """
    Imports delegated stats file from the RIRs.

    Class attributes:
        s3l / dbh : handle to sql3load instance.
    """

    # begin
    def __init__(self, **kwargs):
        """
        Class constructor, receives keyword arguments {rir} and {date}
        """
        self.drir  = kwargs.get('rir','lacnic')
        self.ddate = kwargs.get('date', 'latest')
        self.local_file = kwargs.get('local_file', None)
        self.db_filename = kwargs.get('db_filename', get_tmp_fn(".db") )
        self.as_cache = kwargs.get('as_cache', False)

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
        self.s3l = sql3load(self.s3_template, self.db_filename , "|", "numres", as_cache=self.as_cache, comments_mark="#")
        r = self.s3l.importFile(self.dlg_fn_name)
        self.dbh = self.s3l

        # Add Meta columns
        self._add_columns()
        return
    # end

    # begin
    def _add_columns(self):
        """
        Add meta columns and calculate their corresponding values.
        """
        r1 = self.dbh.addMetaColumn("istart INTEGER")
        r2 = self.dbh.addMetaColumn("iend INTEGER")
        #
        mif = lambda x: self._populate_columns("istart", x)
        p = self.dbh.calculateMetaColumn("istart", mif)
        #
        mif = lambda x: self._populate_columns("iend", x)
        p = self.dbh.calculateMetaColumn("iend", mif)
        #
        r3 = self.dbh.addMetaColumn("prefix VARCHAR(80)")
        mif = lambda x: self._populate_columns("prefix", x)
        p = self.dbh.calculateMetaColumn("prefix", mif)
        #
        r4 = self.dbh.addMetaColumn("equiv INTEGER")
        mif = lambda x: self._populate_columns("equiv", x)
        p = self.dbh.calculateMetaColumn("equiv", mif)
        return r1 and r2 and r3 and r4
    # end

    #begin qs
    def qs(self, w_query):
        '''
        Queries db expecting a single value, returns a single value.
        '''
        rs = self.dbh._rawQuery(w_query)
        k = rs[0].keys()
        return rs[0][k[0]]
    #end qs

    #begin q
    def q(self, w_query):
        '''
        Shorthand for sql3load rawquery, so you can write shorter statements.
        '''
        return self.dbh._rawQuery(w_query)
    #end q

    # begin
    def _download_stats_file(self, **kwargs):
        """
        Downloads stats file for a given rir and date.
        Args 'rir' and 'date' (date can be 'latest')
        Load delegated-stats file and current RIR for given date (YYYYMMDD|latest)

        :param rir=: RIR name
        :param date=: Date as in YYYYMMDD or 'latest'
        """
        dp = dprint()
        # get delegated
        ddate = kwargs.get('date', 'latest')
        drir  = kwargs.get('rir', 'lacnic')
        dp.log("Downloading stat file for RIR %s, date %s...\n" % (self.drir, self.ddate))
        dlg_tmpfile = get_tmp_fn(filename="tmp_delegated-extended-%s-%s" % (drir, ddate) )
        try:
            dlg_f_url = rirconfig.rir_config_data[self.drir]['dlge'][0] % (self.ddate)
            dlg_tmpfile_name = getfile( dlg_f_url, dlg_tmpfile, 3600)
        except:
            print "Failed downloading stats file! url=%s" % (dlg_f_url)
            raise
        if not dlg_tmpfile_name:
            dp.log(" FAILED! url: %s\n" % (dlg_f_url))
            sys.exit(1)
        dp.log(" OK\n")
        return dlg_tmpfile_name
    # end

    # begin
    def _add_equiv_column(self):
        pass
    # end

    #begin
    def _populate_columns(self, w_col_name, w_row):
        """
        Calculates meta columns for the delegated file.
        :param w_col_name:  column being calculated
        :param w_row: dictionary with current row values
        """
        record = {}
        if w_row['type'] == 'ipv4' and w_row['block'] != '*':
            pfx_len = 32 - int( math.log( int(w_row['length']), 2) )
            pfx = ipaddr.IPv4Network(w_row['block'] + "/" + str(pfx_len))
            record['prefix'] = str(pfx)
            record['istart'] = int(pfx.network)
            record['iend'] = int(pfx.broadcast)
            record['equiv'] = (record['iend']-record['istart'])/256 + 1
            return record[w_col_name]
        elif w_row['type'] == 'ipv6' and w_row['block'] != '*':
            pfx_norm_base = pow(2,64)
            #print "row %s" % (dict(w_row))
            pfx = ipaddr.IPv6Network( w_row['block'] + "/" +  str(w_row['length']) )
            record['prefix'] = str(pfx)
            record['istart'] = int(pfx.network) / pfx_norm_base
            record['iend'] = int(pfx.broadcast) / pfx_norm_base
            record['equiv'] = (record['iend'] - record['istart'] + 1) / pow(2,32)
            return record[w_col_name]
        elif w_row['type'] == 'asn' and w_row['block'] != '*':
            record['prefix'] = 'na/asn'
            record['istart'] = int(w_row['block'])
            record['iend'] = int(w_row['block']) + int(w_row['length']) - 1
            record['equiv'] = int(w_row['length'])
            return record[w_col_name]
        else:
            return None
    #end

## end

if __name__ == "__main__":
    print "Not to be run directly"

# END file
#########################################################################################
