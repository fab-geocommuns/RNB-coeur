from django.conf import settings


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


class InvalidOperation(Exception):
    """The operation is not valid"""

    def api_message_with_details(self):
        details = str(self).strip()
        api_message = self.api_message()
        if details:
            api_message = f"{api_message}. {details}"
        return api_message

    def api_message(self):
        raise NotImplementedError("Subclasses must implement this method")


class OperationOnInactiveBuilding(InvalidOperation):
    """Some (many) operations are not permitted on inactive buildings"""

    def api_message(self):
        return "Cette opération est impossible sur un ID-RNB inactif"


class ReactivationNotAllowed(InvalidOperation):
    """The reactivation is not allowed"""

    def api_message(self):
        return "Cet identifiant n'est pas la version la plus récente du bâtiment et ne peut pas être réactivé"


class NotEnoughBuildings(InvalidOperation):
    """Not enough buildings were provided for the operation to succeed"""

    def api_message(self):
        return "Cette opération nécessite au moins deux ID-RNBs"


class InvalidWGS84Geometry(InvalidOperation):
    """The geometry is not a valid WGS 84 geometry"""

    def api_message(self):
        return "La géométrie n'est pas valide"


class BuildingTooLarge(InvalidOperation):
    """The geometry is too large for a building"""

    def api_message(self):
        return f"La surface du bâtiment est trop grande, le maximum autorisé est de {settings.MAX_BUILDING_AREA}m²"


class ImpossibleShapeMerge(InvalidOperation):
    """The given shapes could not be merged"""

    def api_message(self):
        return "Pour fusionner des bâtiments, leurs géométries doivent être des polygones contigus. Veuillez d'abord mettre à jour les géométries des bâtiments"
