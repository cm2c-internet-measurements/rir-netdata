"""
Testing address utils
"""

import unittest
import sys
import uuid
import math

from lacniclabs.utils.addr import pfxExplode

# begin
class Test(unittest.TestCase):

	def setUp(self):
		pass

	def tearDown(self):
		pass

	def testExplodev4(self):
		e = pfxExplode("192.168.1.0/24")
		self.assertTrue(e['type']=='ipv4', "Type should be ipv4")
		self.assertTrue(e['istart']==3232235776, "istart should be 3232235776")
		self.assertTrue(e['pfxlen']==24, "pfxlen should be 24")

	def testExplodev6(self):
		e = pfxExplode("2001:db8:1::/48")
		self.assertTrue(e['type']=='ipv6', "Type should be ipv6")
		self.assertTrue(e['istart']==2306139568115613696L, "istart should be 2306139568115613696L")
		self.assertTrue(e['pfxlen']==48, "pfxlen should be 48")
#end

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    print "TEST Battery: Test address utils"
    unittest.main()
