#########################################################################################
'''
delegated.py: Implements delegated API on top of csv import
(c) carlos@lacnic.net 20151201
'''

from cm2c.csvimport import sql3load
from cm2c.commons.gen.utils import get_tmp_fn
from cm2c.commons.getfile import getfile

## begin
class delegatedStats(object):
    '''
    Imports delegated stats file from the RIRs.
    '''

    dbh = 0
    '''
    dbh: sql3load database handle.
    '''

    # begin
    def __init__(self,w_date, w_rir):
        # get archivo delegated

        ## load into database
        self.s3_template = [ ('name', 'text'), ('age', 'integer'), ('weigth', 'float') ]
        self.s3l = sql3load(self.s3_template, get_tmp_fn(".db") )
        r = self.s3l.importFile("test/test-import.txt")
        self.dbh = sql3load("")
        pass
    # end

    def method1(self,wp1):
        '''
        primer metodo
        '''
        pass
## end

if __name__ == "__main__":
    print "Not to be run directly"

# END file
#########################################################################################
