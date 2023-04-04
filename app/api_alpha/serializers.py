from rest_framework import routers, serializers
from batid.models import Building, Address, ADS, BuildingADS


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id",
            "source",
            "street_number",
            "street_rep",
            "street_name",
            "street_type",
            "city_name",
            "city_zipcode",
        ]


class BuildingSerializer(serializers.ModelSerializer):
    point = serializers.DictField(source="point_geojson")
    addresses = AddressSerializer(many=True, read_only=True)

    class Meta:
        model = Building
        fields = ["rnb_id", "source", "point", "addresses"]


class BuildingsADSSerializer(serializers.ModelSerializer):
    building = serializers.CharField(source="building_rnb_id")

    class Meta:
        model = BuildingADS
        fields = ["building", "operation"]


class ADSSerializer(serializers.ModelSerializer):
    buildings_operations = BuildingsADSSerializer(
        many=True, read_only=True, source="buildingads_set"
    )

    class Meta:
        model = ADS
        fields = ["issue_number", "issue_date", "buildings_operations"]
