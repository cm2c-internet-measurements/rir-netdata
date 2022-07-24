"""
imports.generic

:author: Carlos M. Martinez
:date: July 2022

Generic skeleton for dataset import.
"""

import petl
import pytricia

class GenericImport:
    """
    GenericImport is an abstract class which serves as an skeleton for other imports.
    """

    _datasets = {
        'delegated': None,
        'ris': None,
        'rpki': None
    }

    def __init__(self) -> None:
        pass
    # end def 

    def load(self, pdataset, prir) -> None:
        """
        Loads data
        """
        pass
    # end def

    def save(self) -> None:
        """
        Saves imported data
        """
    
    # end def

# end class

if __name__ == "__main__":
    print("Not to be run directly")
    raise Exception("Not to be run directly")