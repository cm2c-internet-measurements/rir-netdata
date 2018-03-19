#!/usr/bin/env python
# Testing SimpleWhois
#
# (c) carlos@lacnic.net 20180313

import unittest
from SimpleWhois.SimpleWhois import SimpleWhois

## JUST ENOUGH BUILT IN TESTING
class TestSimpleWhois(unittest.TestCase):

    dbfile = "var/netdata-2018-03-07.db"

    def setUp(self):
        self.sw = SimpleWhois(self.dbfile)

    def testClassConstruction(self):
        sw = SimpleWhois(self.dbfile)
        self.assertTrue(sw)
    # end test

    def testDbConnection(self):
        sw = SimpleWhois(self.dbfile)
        self.assertTrue(sw.dbcon)
    # end test

    def testAutnumQueryExisting(self):
        r = self.sw.autnum("6057")
        self.assertEqual(r['cc'], 'UY')
        r = self.sw.autnum("7303")
        self.assertNotEqual(r['cc'], 'UY')
    # end test

    def testAutnumQueryNotExist(self):
        r = self.sw.autnum("XXXX")
        self.assertEqual(r, None)
    ## end test

    def testIpSimple(self):
        r = self.sw.ip("200.40.0.1")
        self.assertTrue(r['cc'] == 'UY')
    ## end test

## END TESTING

if __name__ == '__main__':
    unittest.main()
