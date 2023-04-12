from batid.models import Building
from api_alpha.models import BdgInADS
from rest_framework import serializers


def ads_validate_rnbid(rnb_id):
    if rnb_id == BdgInADS.NEW_STR:
        return
    if not Building.objects.filter(rnb_id=rnb_id).exists():
        raise serializers.ValidationError(f'Building "{rnb_id}" does not exist.')


class BdgInADSValidator:
    def __call__(self, value):
        if value["rnb_id"] == BdgInADS.NEW_STR:
            if not value.get("lat"):
                raise serializers.ValidationError(
                    {"lat": "lat field is required for new buildings."}
                )
            if not value.get("lng"):
                raise serializers.ValidationError(
                    {"lng": "lng field is required for new buildings."}
                )
            return


class ADSValidator:
    def __call__(self, ads):
        self.validate_bdg_once(ads)

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
