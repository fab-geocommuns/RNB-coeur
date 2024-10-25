class BANUnknownCleInterop(Exception):
    """this "clé d'interopérabilité" is not found in the BAN"""


class BANAPIDown(Exception):
    """looks like the BAN API is down"""


class BANBadResultType(Exception):
    """BAN result has not the expected type (ie 'voie' instead of 'numero')"""
