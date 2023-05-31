class BuildingStatus:
    STATUS = [
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

    PUBLIC_STATUS_KEYS = [s["key"] for s in STATUS if s["public"]]
    PRIVATE_STATUS_KEYS = [s["key"] for s in STATUS if not s["public"]]
    ALL_STATUS_KEYS = [s["key"] for s in STATUS]

    STATUS_CHOICES = [(s["key"], s["label"]) for s in STATUS]
