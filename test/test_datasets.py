###############################################################################
# Dataset testing
#
# (c) carlos@lacnic.net 20151109
###############################################################################

import unittest

from cm2c.csvimport.sql3load import sql3load

class TestDatasets(unittest.TestCase):

	def setUp(self):
		self.tp = [ ('name', 'text'), ('age', 'integer'), ('weigth', 'float') ]
		self.im = sql3load(self.tp, "tmp/test.db")

	def test_1plus2(self):
		self.assertEqual(1+2, 3)

	def test_csvimport_iscallable(self):
		self.assertTrue(self.im)

# end class

if __name__ == '__main__':
	unittest.main()

# end file
