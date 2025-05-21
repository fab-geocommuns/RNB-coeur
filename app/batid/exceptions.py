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


class OperationOnInactiveBuilding(Exception):
    """Some (many) operations are not permitted on inactive buildings"""


class NotEnoughBuildings(Exception):
    """Not enough buildings were provided for the operation to succeed"""


class InvalidWGS84Geometry(Exception):
    """The geometry is not a valid WGS 84 geometry"""


class BuildingTooLarge(Exception):
    """The geometry is too large for a building"""


class ImpossibleShapeMerge(Exception):
    """The given shapes could not be merged"""
