import random

from rest_framework import serializers
from batid.models import Building, Address, ADS, BuildingADS
from api_alpha.validators import ads_validate_rnbid


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
    rnb_id = serializers.CharField(validators=[ads_validate_rnbid])

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
    operation = serializers.CharField(required=True)

    class Meta:
        model = BuildingADS
        fields = ["building", "operation"]

    def create(self, validated_data):
        bdg_data = validated_data.pop("building")
        bdg = BdgInAdsSerializer().create(bdg_data)
        return BuildingADS(building=bdg, **validated_data)


class ADSSerializer(serializers.ModelSerializer):
    issue_number = serializers.CharField(required=True, unique=True)
    issue_date = serializers.DateField(required=True, format="%Y-%m-%d")
    buildings_operations = BuildingsADSSerializer(many=True, required=False)

    class Meta:
        model = ADS
        fields = ["issue_number", "issue_date", "buildings_operations"]

    def create(self, validated_data):
        bdg_ops = []
        if "buildings_operations" in validated_data:
            bdg_ops = validated_data.pop("buildings_operations")

        ads = ADS.objects.create(**validated_data)

        for bdg_op_data in bdg_ops:
            bdg_op = BuildingsADSSerializer().create(bdg_op_data)
            bdg_op.ads = ads
            bdg_op.save()

        return ads
