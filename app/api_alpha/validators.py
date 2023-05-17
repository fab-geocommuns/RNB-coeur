from batid.models import Building
from api_alpha.models import BdgInADS
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos.error import GEOSException
from rest_framework import serializers


def ads_validate_rnbid(rnb_id):
    if rnb_id == BdgInADS.NEW_STR:
        return
    if not Building.objects.filter(rnb_id=rnb_id).exists():
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


class ADSValidator:
    def __call__(self, ads):
        self.validate_bdg_once(ads)
        self.validate_has_bdg(ads)

    def validate_has_bdg(self, ads):
        if ads.get("buildings_operations") is None:
            raise serializers.ValidationError(
                {"buildings_operations": "This field is required."}
            )
        if len(ads["buildings_operations"]) == 0:
            raise serializers.ValidationError(
                {"buildings_operations": "At least one building is required."}
            )

    def validate_bdg_once(self, ads):
        if ads.get("buildings_operations") is None:
            return

        rnb_ids = [
            op["building"]["rnb_id"]
            for op in ads["buildings_operations"]
            if op["building"]["rnb_id"] != BdgInADS.NEW_STR
        ]
        if len(rnb_ids) != len(set(rnb_ids)):
            raise serializers.ValidationError(
                {
                    "buildings_operations": "A building can only be present once in an ADS."
                }
            )
