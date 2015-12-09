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

    def setUp(self):
        pass
    ## end

    def tearDown(self):
        pass
    ## end

    def testClassInstantiation(self):
        # test relies on logic put in the setUp method
        pass
    ## end

## end class Test

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    print "TEST Battery: delegated stats from lacniclabs"
    unittest.main()

## END File
##-----------------------------------------------------------------------------------------------------
