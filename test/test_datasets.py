###############################################################################
# Dataset testing
#
# (c) carlos@lacnic.net 20151109
###############################################################################

import unittest

from cm2c.commons.csvimport.sql3load import sql3load

class TestDatasets(unittest.TestCase):
	
	def setUp(self):
		pass

	def test_1plus2(self):
		self.assertEqual(1+2, 3)

	def test_csvimport_iscallable(self):
		tp = [ ('name', 'text'), ('age', 'integer'), ('weigth', 'float') ]
		im = sql3load(tp, "tmp/test.db")
		self.assertTrue(im)

# end class

if __name__ == '__main__':
	unittest.main()

# end file