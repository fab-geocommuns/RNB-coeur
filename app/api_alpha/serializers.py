from batid.models import Address, Building, City
from rest_framework import routers, serializers


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


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ["code_insee", "name"]
