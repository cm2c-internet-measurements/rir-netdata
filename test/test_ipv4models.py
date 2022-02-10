###############################################################################
# IPv4 modularized runout models, testing
#
# (c) carlos@lacnic.net 20151129
###############################################################################

import unittest

from cm2c.csvimport.sql3load import sql3load

class TestDatasets(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

	def test_1plus2(self):
		self.assertEqual(1+2, 3)

# end class

if __name__ == '__main__':
	unittest.main()

# end file
