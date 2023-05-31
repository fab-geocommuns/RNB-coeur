class BuildingStatus:
    STATUS = {
        "constructionProject": "En projet",
        "canceledConstructionProject": "Projet annulé",
        "ongoingConstruction": "Construction en cours",
        "constructed": "Construit",
        "ongoingChange": "En cours de modification",
        "notUsable": "Non utilisable",
        "demolished": "Démoli",
    }
    STATUS_CHOICES = [(k, v) for k, v in STATUS.items()]
