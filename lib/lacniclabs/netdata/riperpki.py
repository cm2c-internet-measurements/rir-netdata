"""
riperpki.py : Imports RIS WHOIS Dumps for both IPv4 and IPv6 into an SQL Lite database

:author: carlos@lacnic.net
:date: 20160526
"""

#########################################################################################

import math
import sys
import ipaddr
from cm2c.csvimport.sql3load import sql3load
from cm2c.commons.gen.utils import get_tmp_fn
from cm2c.commons.gen.getfile import getfile
from cm2c.commons.debug.dprint import dprint
from lacniclabs.etc import rirconfig
from lacniclabs.utils.addr import pfxExplode

# begin class
class ripevalRoaData(object):
    """
    This class imports RIPE-NCC's RPKI validator CSV output

    :author: Carlos M. Martinez, carlos@lacnic.net
    :date: 20160526
    """

    #begin init
    def __init__(self, **kwargs):
        """
        Default constructor
        :param kwargs: name parameters, see below

        :param local_file: pointer to a file in the local filesystem, instead of trying to download the ris whois files
        :param db_filename: pointer to the local database file.
        """
        # import a local file instead of download
        self.local_file = kwargs.get('local_file', None)
        # database filename
        self.db_filename = kwargs.get('db_filename', None)

        # s3_template = [ ('origin_as', 'text'), ('prefix', 'text'), ('viewed_by', 'integer')]
        csv_template = [('origin_as', 'text'), ('prefix', 'text'), ('maxlen', 'integer')]
        self.dbh = sql3load(csv_template, self.db_filename, ",", "roadata")
        self._add_columns() # add meta columns

        if not self.local_file:
            # download Dumps
            self.local_file = self._getRoaCSVExport()
            r = self._addEntries(local_file=self.local_file)
        else:
            r = self._addEntries(local_file=self.local_file)
        #
        return
    # end init

    # begin
    def _getRoaCSVExport(self):
        """
        Downloads RPKI ROA Validator
        """
        dp = dprint()
        dp.log("Downloading dump file for roadata...")
        dlg_tmpfile = get_tmp_fn(filename="rpkivalidator-roadata.csv" )
        # dlg_tmpfile_name4 = getfile(rirconfig.rir_config_data['ripencc']['ris_whois_v4'] , dlg_tmpfile, 86400)
        dlg_tmpfile_name = getfile("http://ripeval.labs.lacnic.net:8080/export.csv" , dlg_tmpfile, 3600)
        return dlg_tmpfile
    #end

    # begin
    def _addEntries(self, **kwargs):
        """
        Adds csv entries from file.
        """
        #
        fn = kwargs.get("local_file", None)
        #
        def p(x):
            sys.stderr.write("[%s]\r" % (x.getKey('inserted-rows'))),
        #
        r = self.dbh.importFile(fn, p, 10000)
        #
        # calculate new columns
        # mif = lambda x: self._populate_columns("type", x)
        mif = lambda x: str.strip(str(x['origin_as']),"AS")
        p = self.dbh.calculateMetaColumn("origin_as2", mif)

        # mif = lambda x: pfxExplode(x['pfx'])['istart']
        def pif(x):
            y = pfxExplode(x['prefix'])
            return y['istart']
        p = self.dbh.calculateMetaColumn("istart", pif)

        #
        mif = lambda x: pfxExplode(x['prefix'])['iend']
        p = self.dbh.calculateMetaColumn("iend", mif)
        mif = lambda x: pfxExplode(x['prefix'])['type']
        p = self.dbh.calculateMetaColumn("type", mif)
        #
        return
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

    # begin
    def _add_columns(self):
        """
        Add meta columns to the roadata database.
        """
        r0 = self.dbh.addMetaColumn("origin_as2 VARCHAR(10)")
        r1 = self.dbh.addMetaColumn("istart UNSIGNED BIG INT")
        r2 = self.dbh.addMetaColumn("iend UNSIGNED BIG INT")
        r3 = self.dbh.addMetaColumn("type VARCHAR(5)")
        r4 = self.dbh.addMetaColumn("pfxlen INTEGER")
        return r1 and r2 and r3 and r4
    #end


    #     dp = dprint()
    #     # get delegated
    #     #ddate = kwargs.get('date', 'latest')
    #     #drir  = kwargs.get('rir', 'lacnic')
    #     dp.log("Downloading dump file for ipv4...")
    #     dlg_tmpfile = get_tmp_fn(filename="ris-whois-dump-ipv4.gz" )
    #     dlg_tmpfile_name4 = getfile(rirconfig.rir_config_data['ripencc']['ris_whois_v4'] , dlg_tmpfile, 86400)
    #     dp.log(" OK\n")
    #     dp.log("Downloading dump file for ipv6...")
    #     dlg_tmpfile = get_tmp_fn(filename="ris-whois-dump-ipv6.gz" )
    #     dlg_tmpfile_name6 = getfile(rirconfig.rir_config_data['ripencc']['ris_whois_v6'] , dlg_tmpfile, 86400)
    #     dp.log(" OK\n")
    #     #
    #     return [dlg_tmpfile_name4, dlg_tmpfile_name6]
    # # end
    #
    # # begin addEntries
    # def addEntries(self, **kwargs):
    #     '''
    #     Add additional entries to the current file
    #     '''
    #     fn = kwargs.get("local_file", None)
    #     #
    #     def p(x):
    #         sys.stderr.write("[%s]\r" % (x.getKey('inserted-rows'))),
    #     #
    #     r = self.dbh.importFile(fn, p, 10000)
    #     #
    #     mif = lambda x: self._populate_columns("type", x)
    #     p = self.dbh.calculateMetaColumn("type", mif)
    #     #
    #     #
    #     mif = lambda x: self._populate_columns("istart", x)
    #     p = self.dbh.calculateMetaColumn("istart", mif)
    #     #
    #     mif = lambda x: self._populate_columns("iend", x)
    #     p = self.dbh.calculateMetaColumn("iend", mif)
    #     #
    #     #
    #     mif = lambda x: self._populate_columns("pfxlen", x)
    #     p = self.dbh.calculateMetaColumn("pfxlen", mif)
    #     #
    #     return True
    # # end addEntries
    #
    # #begin qs
    # def qs(self, w_query):
    #     '''
    #     Queries db expecting a single value, returns a single value.
    #     '''
    #     rs = self.dbh._rawQuery(w_query)
    #     k = rs[0].keys()
    #     return rs[0][k[0]]
    # #end qs
    #
    # #begin q
    # def q(self, w_query):
    #     '''
    #     Shorthand for sql3load rawquery, so you can write shorter statements.
    #     '''
    #     return self.dbh._rawQuery(w_query)
    # #end q
    #
    # # begin
    # def _add_columns(self):
    #     """
    #     Add meta columns to the riswhois database.
    #     """
    #     r1 = self.dbh.addMetaColumn("istart UNSIGNED BIG INT")
    #     r2 = self.dbh.addMetaColumn("iend UNSIGNED BIG INT")
    #     r3 = self.dbh.addMetaColumn("type VARCHAR(5)")
    #     r4 = self.dbh.addMetaColumn("pfxlen INTEGER")
    #     return r1 and r2 and r3 and r4
    # #end
    #
    # #begin
    # def _populate_columns(self, w_col_name, w_row):
    #     """
    #     Calculates meta columns for the delegated file.
    #     :param w_col_name:  column being calculated
    #     :param w_row: dictionary with current row values
    #     """
    #     record = dict(w_row)
    #     #
    #     if w_row['prefix']:
    #         if w_row['prefix'].find(":") != -1:
    #             loc_type = 'ipv6'
    #         else:
    #             loc_type = 'ipv4'
    #     else:
    #         loc_type = 'na'
    #
    #     record['type'] = loc_type
    #     record['pfxlen'] = 0
    #
    #     if record['type'] == 'ipv4' and w_row['prefix']:
    #         record['prefix'] = w_row['prefix']
    #         #print "prefix %s" % (w_row['prefix'])
    #         pfx = ipaddr.IPv4Network(w_row['prefix'])
    #         record['istart'] = int(pfx.network)
    #         record['iend'] = int(pfx.broadcast)
    #         record['pfxlen'] = pfx.prefixlen
    #         # record['equiv'] = (record['iend']-record['istart'])/256 + 1
    #         return record[w_col_name]
    #     elif record['type'] == 'ipv6' and w_row['prefix']:
    #         if w_row['prefix'].startswith("2"):
    #             pfx_norm_base = pow(2,64)
    #             pfx = ipaddr.IPv6Network( w_row['prefix'] )
    #             record['istart'] = int(pfx.network) / pfx_norm_base
    #             record['iend'] = int(pfx.broadcast) / pfx_norm_base
    #             record['pfxlen'] = pfx.prefixlen
    #         else:
    #             record['istart'] = 0
    #             record['iend']   = 0
    #             record['pfxlen'] = 0
    #         # record['equiv'] = (record['iend'] - record['istart'] + 1) / pow(2,32)
    #         return record[w_col_name]
    #     else:
    #         # return record['type']
    #         return record[w_col_name]

    #end
# end class

#########################################################################################
