from datetime import datetime, timezone

from batid.models import Building, City
from batid.services.source import Source
from django.core.serializers import serialize


def export_city(insee_code: str) -> str:
    src = Source("export")
    src.set_param("city", insee_code)
    src.set_param("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    city = City.objects.get(code_insee=insee_code)

    # NB : filtrer pour ne conserver que les bâtiments réels
    bdgs = Building.objects.filter(shape__intersects=city.shape).order_by("rnb_id")

    geojson = serialize(
        "geojson",
        bdgs,
        geometry_field="shape",
        fields=("rnb_id", "status", "ext_ids"),
    )

    # remove the id field from the features
    # I would have preferred to serialize directly without the id field
    # but since Django 4.2 the id field is included.
    # https://github.com/django/django/pull/15740
    # https://stackoverflow.com/questions/1615649/remove-pk-field-from-django-serialized-objects
    import json

    data = json.loads(geojson)
    for f in data["features"]:
        del f["id"]
    geojson = json.dumps(data)

    with open(src.path, "w") as f:
        f.write(geojson)

    return src.path
