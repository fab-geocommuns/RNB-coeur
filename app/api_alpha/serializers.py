import random

from rest_framework import serializers
from batid.models import Building, Address, ADS, BuildingADS, City
from batid.logic.ads import ADS as ADSLogic
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


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ["code_insee", "name"]


class BdgInAdsSerializer(serializers.ModelSerializer):
    lat = serializers.FloatField(
        required=False, max_value=90, min_value=-90, source="point_lat"
    )
    lng = serializers.FloatField(
        required=False,
        max_value=180,
        min_value=-180,
        source="point_lng",
    )
    rnb_id = serializers.CharField(validators=[ads_validate_rnbid])

    class Meta:
        model = Building
        fields = ["rnb_id", "lat", "lng"]
        validators = [BdgInADSValidator()]

    def create(self, validated_data):
        if validated_data.get("rnb_id") == BdgInADS.NEW_STR:
            lat = validated_data.pop("point_lat")
            lng = validated_data.pop("point_lng")
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

    def update(self, bdg_ads, validated_data):
        validated_data.pop("building")
        for attr, value in validated_data.items():
            setattr(bdg_ads, attr, value)
        return bdg_ads


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
    insee_code = serializers.CharField(required=True)

    class Meta:
        model = ADS
        fields = ["issue_number", "issue_date", "insee_code", "buildings_operations"]
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

    def update(self, ads, validated_data):
        data_bdg_ops = []
        if "buildings_operations" in validated_data:
            data_bdg_ops = validated_data.pop("buildings_operations")

        for attr, value in validated_data.items():
            setattr(ads, attr, value)
        ads.save()

        if data_bdg_ops:
            for data_bdg_op in data_bdg_ops:
                # First we check if the building is already in the ADS
                adslogic = ADSLogic(ads)
                if adslogic.concerns_rnb_id(data_bdg_op["building"]["rnb_id"]):
                    bdg_op = adslogic.get_op_by_rnbid(data_bdg_op["building"]["rnb_id"])
                    bdg_op = BuildingsADSSerializer().update(bdg_op, data_bdg_op.copy())
                else:
                    bdg_op = BuildingsADSSerializer().create(data_bdg_op.copy())
                    bdg_op.ads = ads
                bdg_op.save()

            # We remove operations which are in the ADS but not in sent data (matching on RNB ID)
            data_rnb_ids = [b["building"]["rnb_id"] for b in data_bdg_ops]
            for model_bdg_op in ads.buildings_operations.all():
                if model_bdg_op.building.rnb_id not in data_rnb_ids:
                    model_bdg_op.delete()

        return ads
