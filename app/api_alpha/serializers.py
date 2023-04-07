import random

from rest_framework import serializers
from batid.models import Building, Address, ADS, BuildingADS
from api_alpha.validators import (
    ads_validate_rnbid,
    BdgInADSValidator,
    ADSValidator,
)
from api_alpha.models import BuildingADS as BuildingADSModel, BdgInADS
from rest_framework.validators import UniqueValidator
from rnbid.generator import generate_id


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
    lat = serializers.FloatField(
        write_only=True, required=False, max_value=90, min_value=-90
    )
    lng = serializers.FloatField(
        write_only=True, required=False, max_value=180, min_value=-180
    )
    rnb_id = serializers.CharField(validators=[ads_validate_rnbid])

    class Meta:
        model = Building
        fields = ["rnb_id", "lat", "lng"]
        validators = [BdgInADSValidator()]

    def create(self, validated_data):
        if validated_data.get("rnb_id") == BdgInADS.NEW_STR:
            lat = validated_data.pop("lat")
            lng = validated_data.pop("lng")
            point = "POINT({} {})".format(lng, lat)
            validated_data["point"] = point
            validated_data["rnb_id"] = generate_id()
            return super().create(validated_data)
        else:
            return Building.objects.get(rnb_id=validated_data["rnb_id"])


class BuildingsADSSerializer(serializers.ModelSerializer):
    building = BdgInAdsSerializer()
    operation = serializers.ChoiceField(
        required=True,
        choices=BuildingADSModel.OPERATIONS,
        error_messages={
            "invalid_choice": "'{input}' is not a valid operation. Valid operations are: "
            + f"{BuildingADSModel.OPERATIONS}."
        },
    )

    class Meta:
        model = BuildingADS
        fields = ["building", "operation"]

    def create(self, validated_data):
        bdg_data = validated_data.pop("building")
        bdg = BdgInAdsSerializer().create(bdg_data)
        return BuildingADS(building=bdg, **validated_data)


class ADSSerializer(serializers.ModelSerializer):
    issue_number = serializers.CharField(
        required=True,
        validators=[
            UniqueValidator(
                queryset=ADS.objects.all(), message="This issue number already exists"
            )
        ],
    )
    issue_date = serializers.DateField(required=True, format="%Y-%m-%d")
    buildings_operations = BuildingsADSSerializer(many=True, required=False)

    class Meta:
        model = ADS
        fields = ["issue_number", "issue_date", "buildings_operations"]
        validators = [ADSValidator()]

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
