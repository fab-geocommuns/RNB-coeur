from batid.models import Building
from api_alpha.services import BdgInADS
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos.error import GEOSException
from rest_framework import serializers
from batid.services.rnb_id import clean_rnb_id


def ads_validate_rnbid(rnb_id):
    if rnb_id == BdgInADS.NEW_STR:
        return

    clean_id = clean_rnb_id(rnb_id)
    if not Building.objects.filter(rnb_id=clean_id).exists():
        raise serializers.ValidationError(f'Building "{rnb_id}" does not exist.')


class BdgInADSValidator:
    def __call__(self, value):
        if value["rnb_id"] == BdgInADS.NEW_STR:
            geojson = value.get("ads_geojson")

            if not geojson:
                raise serializers.ValidationError(
                    {
                        "geometry": "GeoJSON Point or MultiPolygon is required for new buildings."
                    }
                )

            if geojson["type"] not in ("Point", "MultiPolygon"):
                raise serializers.ValidationError(
                    {"geometry": "GeoJSON must be a Point or a MultiPolygon."}
                )

            try:
                geometry = GEOSGeometry(str(geojson))
            except GEOSException:
                raise serializers.ValidationError({"geometry": "GeoJSON is invalid."})

            if not geometry.valid:
                raise serializers.ValidationError(
                    {"geometry": f"GeoJSON is invalid: {geometry.valid_reason}"}
                )

            return


class ADSCitiesValidator:
    def __call__(self, cities):
        if len(cities) == 0:
            raise serializers.ValidationError(
                {"buildings_operations": ["Buildings are in an unknown city"]}
            )

        if len(cities) > 1:
            raise serializers.ValidationError(
                {"buildings_operations": ["Buildings must be in only one city"]}
            )


class ADSValidator:
    def __call__(self, data):
        self.validate_bdg_once(data)
        self.validate_has_bdg(data)

    def validate_has_bdg(self, data):
        if data.get("buildings_operations") is None:
            raise serializers.ValidationError(
                {"buildings_operations": "This field is required."}
            )
        if len(data["buildings_operations"]) == 0:
            raise serializers.ValidationError(
                {"buildings_operations": "At least one building is required."}
            )

    def validate_bdg_once(self, data):
        if data.get("buildings_operations") is None:
            return

        rnb_ids = [
            op["building"]["rnb_id"]
            for op in data["buildings_operations"]
            if op["building"]["rnb_id"] != BdgInADS.NEW_STR
        ]
        if len(rnb_ids) != len(set(rnb_ids)):
            raise serializers.ValidationError(
                {
                    "buildings_operations": "A building can only be present once in an ADS."
                }
            )
