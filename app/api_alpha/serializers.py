import random

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
    point = serializers.DictField(source="point_geojson", read_only=True)
    addresses = AddressSerializer(many=True, read_only=True)
    source = serializers.CharField(read_only=True)

    class Meta:
        model = Building
        fields = ["rnb_id", "source", "point", "addresses"]


class BdgInAdsSerializer(serializers.ModelSerializer):
    lat = serializers.FloatField(write_only=True, required=False)
    lng = serializers.FloatField(write_only=True, required=False)

    class Meta:
        model = Building
        fields = ["rnb_id", "lat", "lng"]

    def create(self, validated_data):
        if validated_data.get("rnb_id") == "new":
            lat = validated_data.pop("lat")
            lng = validated_data.pop("lng")
            point = "POINT({} {})".format(lng, lat)
            validated_data["point"] = point
            validated_data[
                "rnb_id"
            ] = f"{random.choice(range(10000))}-{random.choice(range(10000))}"  # todo : generate random rnb id

            return super().create(validated_data)
        else:
            return Building.objects.get(rnb_id=validated_data["rnb_id"])


class BuildingsADSSerializer(serializers.ModelSerializer):
    building = BdgInAdsSerializer()

    class Meta:
        model = BuildingADS
        fields = ["building", "operation"]

    def create(self, validated_data):
        bdg_data = validated_data.pop("building")
        bdg = BuildingSerializer().create(bdg_data)
        return BuildingADS.objects.create(building=bdg, **validated_data)


class ADSSerializer(serializers.ModelSerializer):
    buildings_operations = BuildingsADSSerializer(many=True, source="buildingads_set")

    class Meta:
        model = ADS
        fields = ["issue_number", "issue_date", "buildings_operations"]

    def create(self, validated_data):
        bdgadss = validated_data.pop("buildingads_set")

        ads = ADS.objects.create(**validated_data)

        for idx, bdgads in enumerate(bdgadss):
            bdgadss[idx]["ads"] = ads

        BuildingsADSSerializer(many=True).create(bdgads)
        return ads
