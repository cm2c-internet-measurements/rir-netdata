"""
rishois.py : Importos RIS WHOIS Dumps for both IPv4 and IPv6 into an SQL Lite database

:author: carlos@lacnic.net
:date: 20151221
"""

#########################################################################################

import math
import ipaddr
from cm2c.csvimport.sql3load import sql3load
from cm2c.commons.gen.utils import get_tmp_fn
from cm2c.commons.gen.getfile import getfile
from cm2c.commons.debug.dprint import dprint
from lacniclabs.etc import rirconfig

# begin class
class risWhois(object):

    #begin init
    def __init__(self, **kwargs):
        # set ip version
        self.type = kwargs.get('ipversion', 'ipv4')
        # import a local file instead of download
        self.local_file = kwargs.get('local_file', None)
        # database filename
        self.db_filename = kwargs.get('db_filename', get_tmp_fn(".db"))

        if not self.local_file:
            # download Dumps
            # import Dump
            pass

        s3_template = [ ('origin_as', 'text'), ('prefix', 'text'), ('viewed_by', 'integer')]
        self.dbh = sql3load(s3_template, self.db_filename, "\t", "riswhois")
        r = self.dbh.importFile(self.local_file, "\t")
    # end init

    # begin addEntries
    def addEntries(self, **kwargs):
        '''
        Add additional entries to the current file
        '''
        fn = kwargs.get("local_file", None)
        r = self.dbh.importFile(fn, "\t")
        #
        mif = lambda x: self._populate_columns("type", x)
        p = self.dbh.calculateMetaColumn("type", mif)
        #
        #
        mif = lambda x: self._populate_columns("istart", x)
        p = self.dbh.calculateMetaColumn("istart", mif)
        #
        mif = lambda x: self._populate_columns("iend", x)
        p = self.dbh.calculateMetaColumn("iend", mif)
        return True
    # end addEntries

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
        Shorthand for query
        '''
        return self.dbh._rawQuery(w_query)
    #end q

    # begin
    def _add_columns(self):
        r1 = self.dbh.addMetaColumn("istart UNSIGNED BIG INT")
        r2 = self.dbh.addMetaColumn("iend UNSIGNED BIG INT")
        r3 = self.dbh.addMetaColumn("type VARCHAR(5)")
        #
        mif = lambda x: self._populate_columns("type", x)
        p = self.dbh.calculateMetaColumn("type", mif)
        #
        mif = lambda x: self._populate_columns("istart", x)
        p = self.dbh.calculateMetaColumn("istart", mif)
        #
        mif = lambda x: self._populate_columns("iend", x)
        p = self.dbh.calculateMetaColumn("iend", mif)
        #
        return r1 and r2
    #end

    #begin
    def _populate_columns(self, w_col_name, w_row):
        """
        Calculates meta columns for the delegated file.
        :param w_col_name:  column being calculated
        :param w_row: dictionary with current row values
        """
        record = {}
        #
        if w_row['prefix']:
            if w_row['prefix'].find(":") != -1:
                loc_type = 'ipv6'
            else:
                loc_type = 'ipv4'
        else:
            loc_type = 'na'
        record['type'] = loc_type

        if record['type'] == 'ipv4' and w_row['prefix']:
            record['prefix'] = w_row['prefix']
            #print "prefix %s" % (w_row['prefix'])
            pfx = ipaddr.IPv4Network(w_row['prefix'])
            record['istart'] = int(pfx.network)
            record['iend'] = int(pfx.broadcast)
            # record['equiv'] = (record['iend']-record['istart'])/256 + 1
            return record[w_col_name]
        elif record['type'] == 'ipv6' and w_row['prefix'] and w_row['prefix']!="::/0":
            pfx_norm_base = pow(2,64)
            #print "row %s" % (dict(w_row))
            pfx = ipaddr.IPv6Network( w_row['prefix'] )
            # print pfx
            record['istart'] = int(pfx.network) / pfx_norm_base
            record['iend'] = int(pfx.broadcast) / pfx_norm_base
            # record['equiv'] = (record['iend'] - record['istart'] + 1) / pow(2,32)
            return record[w_col_name]
        else:
            return record['type']
    #end
# end class

#########################################################################################
