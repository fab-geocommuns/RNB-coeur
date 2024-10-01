from rest_framework import serializers

from batid.models import Building


def ads_validate_rnbid(rnb_id):

    if not Building.objects.filter(rnb_id=rnb_id).exists():
        raise serializers.ValidationError(f'Building "{rnb_id}" does not exist.')


def bdg_is_active(rnb_id: str):

    if Building.objects.filter(rnb_id=rnb_id, is_active=False).exists():
        raise serializers.ValidationError(f'Building "{rnb_id}" is not active.')


class BdgInADSValidator:
    def __call__(self, value):

        rnb_id = value.get("rnb_id", None)
        shape = value.get("shape", None)

        if rnb_id is None and shape is None:
            raise serializers.ValidationError("Either rnb_id or shape is required.")

        if rnb_id is not None and shape is not None:
            raise serializers.ValidationError(
                "You can't provide a rnb_id and a shape, you should remove the shape."
            )

        # if shape is not None:
        #     try:
        #         print("-- transform !!")
        #         GEOSGeometry(shape)
        #
        #     except GEOSException as e:
        #         raise serializers.ValidationError("Invalid GeoJSON geometry.")


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
            op["rnb_id"]
            for op in data["buildings_operations"]
            if "rnb_id" in op and op["rnb_id"] is not None
        ]
        if len(rnb_ids) != len(set(rnb_ids)):
            raise serializers.ValidationError(
                {"buildings_operations": "A RNB id can only be present once in an ADS."}
            )
