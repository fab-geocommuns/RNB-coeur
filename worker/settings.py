import os

settings = {
    "MIN_BDG_AREA": float(os.environ.get("MIN_BDG_AREA")),
    "DEFAULT_SRID": int(os.environ.get("DEFAULT_SRID")),
}