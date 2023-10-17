from typing import Optional
from rest_framework import serializers
from batid.models import Building, BuildingStatus, ADS, BuildingADS, City, Address
from batid.services.models_gears import ADSGear as ADSLogic
from api_alpha.validators import (
    ads_validate_rnbid,
    BdgInADSValidator,
    ADSValidator,
)
from api_alpha.services import BuildingADS as BuildingADSLogic, BdgInADS
from rest_framework.validators import UniqueValidator
from batid.services.rnb_id import generate_rnb_id, clean_rnb_id
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon

from batid.services.search_bdg import BuildingSearch


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
            "city_insee_code",
        ]


class BuildingStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuildingStatus
        fields = ["type", "happened_at", "label", "is_current"]


class BuildingSerializer(serializers.ModelSerializer):
    point = serializers.DictField(source="point_geojson", read_only=True)
    addresses = AddressSerializer(many=True, read_only=True)
    status = BuildingStatusSerializer(read_only=True, many=True)
    ext_bdtopo_id = serializers.CharField(read_only=True)

    class Meta:
        model = Building
        fields = ["rnb_id", "status", "point", "addresses", "ext_bdtopo_id"]


class GuessBuildingSerializer(serializers.ModelSerializer):
    score = serializers.FloatField(read_only=True)
    point = serializers.DictField(source="point_geojson", read_only=True)
    addresses = AddressSerializer(many=True, read_only=True)
    status = BuildingStatusSerializer(read_only=True, many=True)
    ext_bdtopo_id = serializers.CharField(read_only=True)

    class Meta:
        model = Building
        fields = ["rnb_id", "score", "status", "point", "addresses", "ext_bdtopo_id"]


class CityADSSerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ["code_insee", "name"]


class BdgInAdsSerializer(serializers.ModelSerializer):
    geometry = serializers.DictField(source="ads_geojson", required=False)
    rnb_id = serializers.CharField(validators=[ads_validate_rnbid])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.custom_id = None

    class Meta:
        model = Building
        fields = ["rnb_id", "geometry"]
        validators = [BdgInADSValidator()]

    def to_internal_value(self, data):
        # Keep the custom id
        custom_id = data.get("custom_id", None)
        if custom_id:
            self.custom_id = custom_id

        return super().to_internal_value(data)

    def to_representation(self, instance):
        ret = super().to_representation(instance)

        if self.custom_id:
            ret["custom_id"] = self.custom_id

        return ret

    def create(self, validated_data):
        if validated_data.get("rnb_id") == BdgInADS.NEW_STR:
            geojson = validated_data.pop("ads_geojson")

            geometry = GEOSGeometry(str(geojson))

            if geometry.geom_type == "Point":
                validated_data["point"] = f"{geometry}"

            if geometry.geom_type == "MultiPolygon":
                validated_data["shape"] = f"{geometry}"
                validated_data["point"] = f"{geometry.point_on_surface}"

            validated_data["rnb_id"] = generate_rnb_id()
            validated_data["source"] = "ADS"
            building = super().create(validated_data)
            return building
        elif validated_data.get("rnb_id") == BdgInADS.GUESS_STR:
            geojson = validated_data.pop("ads_geojson")
            geometry = GEOSGeometry(str(geojson))

            if geometry.geom_type == "MultiPolygon":
                validated_data["shape"] = f"{geometry}"
                validated_data["point"] = f"{geometry.point_on_surface}"

            bdg = self.guess_bdg(geometry)
            if isinstance(bdg, Building):
                return bdg

            if bdg is None:
                validated_data["rnb_id"] = generate_rnb_id()
                validated_data["source"] = "ADS"
                building = super().create(validated_data)
                return building

        else:
            clean_id = clean_rnb_id(validated_data["rnb_id"])
            bdg = Building.objects.get(rnb_id=clean_id)

            return bdg

    def guess_bdg(self, mp: MultiPolygon) -> Optional[Building]:
        """Try to guess the building from the MultiPolygon"""

        search = BuildingSearch()
        search.set_params(**{"poly": mp[0]})
        qs = search.get_queryset()
        if len(qs) == 1:
            return qs[0]

        return None


class BuildingsADSSerializer(serializers.ModelSerializer):
    building = BdgInAdsSerializer()
    operation = serializers.ChoiceField(
        required=True,
        choices=BuildingADSLogic.OPERATIONS,
        error_messages={
            "invalid_choice": "'{input}' is not a valid operation. Valid operations are: "
            + f"{BuildingADSLogic.OPERATIONS}."
        },
    )
    creator = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = BuildingADS
        fields = ["building", "operation", "creator"]

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
    file_number = serializers.CharField(
        required=True,
        validators=[
            UniqueValidator(
                queryset=ADS.objects.all(), message="This issue number already exists"
            )
        ],
    )
    decided_at = serializers.DateField(required=True, format="%Y-%m-%d")
    buildings_operations = BuildingsADSSerializer(many=True, required=False)
    city = CityADSSerializer(required=False, read_only=True)
    creator = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._errors = []

    class Meta:
        model = ADS
        fields = [
            "file_number",
            "decided_at",
            "city",
            "buildings_operations",
            "creator",
        ]
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
            # First, we remove operations which are in the ADS but not in sent data (matching on RNB ID)
            data_rnb_ids = [b["building"]["rnb_id"] for b in data_bdg_ops]
            for model_bdg_op in ads.buildings_operations.all():
                if model_bdg_op.building.rnb_id not in data_rnb_ids:
                    model_bdg_op.delete()

            # Then we add the new operations
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

        return ads
