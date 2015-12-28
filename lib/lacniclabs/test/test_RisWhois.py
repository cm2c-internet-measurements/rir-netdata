##-----------------------------------------------------------------------------------------------------
'''
Test Battery for the RIS WHOIS Dump CSV Import
Created on Dec 21, 2015

@author: marcelo, carlos@xt6.us

@changelog:
'''
import unittest
import sys
import uuid

import math
import ipaddr
from lacniclabs.netdata.riswhois import risWhois

#--
class Test(unittest.TestCase):

    _setuponce_done = False
    _use_local_test_data = True

    def setUp(self):
        if not self.__class__._setuponce_done:
            self.__class__._setuponce_done = True
            # self.__class__.rwr = risWhois(type="ipv4", local_file="tmp/ris-whois-short")
            if self.__class__._use_local_test_data:
                self.__class__.rwr = risWhois(local_file="tmp/ris-whois-short", db_filename="tmp/riswhois.db")
            else:
                self.__class__.rwr = risWhois(db_filename="tmp/riswhois2.db")
                # self.__class__.rwr = risWhois(db_filename=":memory:")
        else:
            # print "Tests already set up!"
            pass
    ## end

    def tearDown(self):
        pass
    ## end

    def testClassInstantiation(self):
        # test relies on logic put in the setUp method
        pass
    ## end

    def testCountRowsLoaded(self):
        #
        ir = self.__class__.rwr.qs("SELECT count(*) FROM riswhois")
        # print "imported rows %s" % (ir)
        self.assertTrue(int(ir) > 1000, "Failed importing more than 1k rows")
    # end

    def testFieldQueries(self):
        rs1 = self.__class__.rwr.q("SELECT count(*) AS cnt FROM riswhois WHERE viewed_by > 5 ")
        c = rs1[0]['cnt']
        # print str(rs1)
        self.assertTrue(int(c)>0, "No networks viewed by more than 5 sensors")
    # end

    def testAddedColumns(self):
        #rs1 = self.__class__.rwr._add_columns()
        #self.assertTrue(rs1, "Failed column creation")
        #
        rs2 = self.__class__.rwr.qs("SELECT count(*) AS cnt FROM riswhois WHERE type='ipv4'")
        msg2 = "Could not find type ipv4, rs %s " % (str(rs2))
        self.assertTrue(int(rs2)>10, msg2)
        #
        rs2 = self.__class__.rwr.qs("SELECT count(*) AS cnt FROM riswhois WHERE istart > 32106496 AND iend < 32107775")
        self.assertTrue(int(rs2)>1, "Could not compare istart and iend, rs %s " % (str(rs2)) )
        #
        rs3 = self.__class__.rwr.qs("SELECT count(*) AS cnt FROM riswhois WHERE type='ipv4' AND pfxlen=24")
        self.assertTrue(int(rs3)>10, "Could not find ipv4 pfx with pfxlen=24, rs %s " % (str(rs3)) )
        #
        rs3 = self.__class__.rwr.qs("SELECT count(*) AS cnt FROM riswhois WHERE type='ipv6' AND pfxlen=32")
        self.assertTrue(int(rs3)>10, "Could not find ipv6 pfx with pfxlen=32, rs %s " % (str(rs3)) )        
        #
    # end

    # begin
    def testAddEntriesIPv6(self):
        rs1 = self.__class__.rwr.addEntries(local_file="tmp/ris-whois-short6")
        self.assertTrue(rs1, "Could not add ipv6 entries")
        rs2 = self.__class__.rwr.qs("SELECT count(*) as CNT FROM riswhois where type='ipv6'")
        c2 = int(rs2)
        self.assertTrue(c2 > 100, "Could not load enough ipv6 entries, expected more than 100, got %s" % (c2))
    # end

## end class Test

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    print "TEST Battery: RIS WHOIS Dump from lacniclabs"
    unittest.main()

## END File
##-----------------------------------------------------------------------------------------------------
