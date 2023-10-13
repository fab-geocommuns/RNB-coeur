from batid.models import BuildingStatus as BuildingStatusModel


class BuildingStatus:
    PRIVATE_TYPES = [
        BuildingStatusModel.CONSTRUCTION_PROJECT,
        BuildingStatusModel.CANCELED_CONSTRUCTION_PROJECT,
    ]

    PUBLIC_TYPES = [
        BuildingStatusModel.ONGOING_CONSTRUCTION,
        BuildingStatusModel.CONSTRUCTED,
        BuildingStatusModel.ONGOING_CHANGE,
        BuildingStatusModel.NOT_USABLE,
        BuildingStatusModel.DEMOLISHED,
    ]

    ALL_TYPES = PUBLIC_TYPES + PRIVATE_TYPES

    DEFAULT_DISPLAY_TYPES = [
        BuildingStatusModel.ONGOING_CONSTRUCTION,
        BuildingStatusModel.CONSTRUCTED,
        BuildingStatusModel.ONGOING_CHANGE,
        BuildingStatusModel.NOT_USABLE,
    ]

    # Those are the status which trigger the creation of a "constructed" status
    # if the building does not have one
    POST_CONSTRUCTED_TYPES = [
        BuildingStatusModel.ONGOING_CHANGE,
        BuildingStatusModel.NOT_USABLE,
        BuildingStatusModel.DEMOLISHED,
    ]
