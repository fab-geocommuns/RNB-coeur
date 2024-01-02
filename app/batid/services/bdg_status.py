class BuildingStatus:
    TYPES = [
        {"key": "constructionProject", "label": "En projet", "public": False},
        {
            "key": "canceledConstructionProject",
            "label": "Projet annulé",
            "public": False,
        },
        {
            "key": "ongoingConstruction",
            "label": "Construction en cours",
            "public": True,
        },
        {"key": "constructed", "label": "Construit", "public": True},
        {"key": "ongoingChange", "label": "En cours de modification", "public": True},
        {
            "key": "notUsable",
            "label": "Non utilisable",
            "public": True,
        },
        {"key": "demolished", "label": "Démoli", "public": True},
    ]

    PUBLIC_TYPES_KEYS = [s["key"] for s in TYPES if s["public"]]
    PRIVATE_TYPES_KEYS = [s["key"] for s in TYPES if not s["public"]]
    ALL_TYPES_KEYS = [s["key"] for s in TYPES]

    # ####### REAL_BUILDINGS_STATUS #######
    # Those are the status for buildings having a real physical presence in the world
    # It is used in many places:
    # eg: default status values in the listing API or the Candidate Inspector to match buildings
    REAL_BUILDINGS_STATUS = [
        "ongoingConstruction",
        "constructed",
        "ongoingChange",
        "notUsable",
    ]

    # Those are the status which trigger the creation of a "constructed" status
    # if the building does not have one
    POST_CONSTRUCTED_KEYS = [
        "ongoingChange",
        "notUsable",
        "demolished",
    ]

    TYPES_CHOICES = [(s["key"], s["label"]) for s in TYPES]

    @classmethod
    def get_label(cls, key):
        return next(s["label"] for s in cls.TYPES if s["key"] == key)
