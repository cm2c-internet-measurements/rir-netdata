##-----------------------------------------------------------------------------------------------------
'''
Test Battery for the DelegatedStats CSV Import
Created on Nov 23, 2015

@author: marcelo, carlos@xt6.us

@changelog:
'''
import unittest
import sys
import uuid

from lacniclabs.delegated.delegated import delegatedStats

#--
class Test(unittest.TestCase):

    _setuponce_done = False
    dsreader = None

    def setUp(self):
        if not self._setuponce_done:
            self.__class__.dsreader = delegatedStats(local_file="tmp/delegated-extended-lacnic-short")
            self.__class__._setuponce_done = True
        else:
            pass
    ## end

    def tearDown(self):
        pass
    ## end

    def testClassInstantiation(self):
        # test relies on logic put in the setUp method
        pass
    ## end

    def testQueryDelegated1(self):
        rs1 = self.__class__.dsreader.dbh._rawQuery("SELECT count(*) as cnt FROM numres")
        # rs1 = self.dsreader.dbh._rawQuery(".schema")
        # print str(rs1)
        rowCount = rs1[0]['cnt']
        self.assertTrue(rowCount>1000)
    ## end

    def testQueryDelegated2(self):
        rs1 = self.__class__.dsreader.dbh._rawQuery("SELECT count(*) as cnt FROM numres WHERE status='allocated'")
        # rs1 = self.dsreader.dbh._rawQuery(".schema")
        # print "allocated %s" % (str(rs1))
        rowCount = rs1[0]['cnt']
        self.assertTrue(rowCount>1000)
    ## end

    def testQueryDelegated3(self):
        rs1 = self.__class__.dsreader.dbh._rawQuery("SELECT count(*) as cnt FROM numres WHERE status='available'")
        # rs1 = self.dsreader.dbh._rawQuery(".schema")
        # print "available %s" % (str(rs1))
        rowCount = rs1[0]['cnt']
        self.assertTrue(rowCount>5)
    ## end

    def testQueryDelegated3(self):
        rs1 = self.__class__.dsreader.dbh._rawQuery("SELECT count(*) as cnt FROM numres WHERE status='reserved'")
        # rs1 = self.dsreader.dbh._rawQuery(".schema")
        # print "reserved %s" % (str(rs1))
        rowCount = rs1[0]['cnt']
        self.assertTrue(rowCount>5)
    ## end

    def testAddPrefixColumn(self):
        rs = self.__class__.dsreader._add_prefix_column()
        self.assertTrue(rs, "Error creating prefix column")
    ## end

    def testAddEquivColumn(self):
        rs = self.__class__.dsreader._add_equiv_column()
        self.assertTrue(rs, "Error creating equiv column")
    ## end

    def testAddNumBeginAndEnd(self):
        rs = self.__class__.dsreader._add_numeric_columns()
        self.assertTrue(rs, "Error creating numeric columns")
    ## end

## end class Test

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    print "TEST Battery: delegated stats from lacniclabs"
    unittest.main()

## END File
##-----------------------------------------------------------------------------------------------------
