class BANUnknownCleInterop(Exception):
    """this "clé d'interopérabilité" is not found in the BAN"""


class BANAPIDown(Exception):
    """looks like the BAN API is down""" 

class BANBadRequest(Exception):
    """BAN API returns a 400 error code"""

class BANBadResultType(Exception):
    """BAN result has not the expected type (ie 'voie' instead of 'numero')"""


class ContributionFixTooBroad(Exception):
    """The criteria given to select contributions are not specific enough"""


class PlotUnknown(Exception):
    """The given plot id is not in the RNB database"""
