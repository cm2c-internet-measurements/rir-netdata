"""
riperpki.py : Imports RIS WHOIS Dumps for both IPv4 and IPv6 into an SQL Lite database

:author: carlos@lacnic.net
:date: 20160526
:date: 20170328
:date: 20170719

Changelog:
- 20170719 fixed prefixlen in roas not getting updated
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
    :modified: 20170715
    """

    #begin init
    def __init__(self, **kwargs):
        """
        Default constructor
        :param kwargs: name parameters, see below

        :param local_file: pointer to a file in the local filesystem, instead of trying to download the ris whois files
        :param db_filename: pointer to the local database file.
        :param url: url of a ripe validator exporting csv file
        """
        # import a local file instead of download
        self.local_file = kwargs.get('local_file', None)
        # database filename
        self.db_filename = kwargs.get('db_filename', None)
        # set url or default to the well known one
        self.validator_url = kwargs.get('url', "http://ripeval.labs.lacnic.net:8080/export.csv")

        # s3_template = [ ('origin_as', 'text'), ('prefix', 'text'), ('viewed_by', 'integer')]
        csv_template = [('origin_as', 'text'), ('prefix', 'text'), ('maxlen', 'integer'), ('ta', 'text')]
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
        dlg_tmpfile_name = getfile(self.validator_url , dlg_tmpfile, 3600)
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
        # calculate new columns: origin_as2 strips the leading AS from origin_as
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
        mif = lambda x: pfxExplode(x['prefix'])['equiv']
        p = self.dbh.calculateMetaColumn("equiv", mif)
        mif = lambda x: pfxExplode(x['prefix'])['pfxlen']
        p = self.dbh.calculateMetaColumn("pfxlen", mif)
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
        r5 = self.dbh.addMetaColumn("equiv INTEGER")
        return r1 and r2 and r3 and r4 and r5
    #end


# end class

#########################################################################################
