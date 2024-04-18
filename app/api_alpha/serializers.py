from typing import Optional

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import MultiPolygon
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from api_alpha.services import BdgInADS
from api_alpha.services import BuildingADS as BuildingADSLogic
from api_alpha.validators import ads_validate_rnbid
from api_alpha.validators import ADSValidator
from api_alpha.validators import BdgInADSValidator
from batid.models import Address
from batid.models import ADS
from batid.models import Building
from batid.models import BuildingADS
from batid.models import City
from batid.models import Contribution
from batid.services.guess_bdg import BuildingGuess
from batid.services.models_gears import ADSGear as ADSLogic
from batid.services.rnb_id import clean_rnb_id
from batid.services.rnb_id import generate_rnb_id


class RNBIdField(serializers.CharField):
    def to_internal_value(self, data):
        return clean_rnb_id(data)


class ContributionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contribution
        fields = ["rnb_id", "text"]


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


class BuildingSerializer(serializers.ModelSerializer):
    point = serializers.DictField(source="point_geojson", read_only=True)
    addresses = AddressSerializer(many=True, read_only=True)
    ext_ids = serializers.JSONField(read_only=True)

    class Meta:
        model = Building
        fields = ["rnb_id", "status", "point", "addresses", "ext_ids", "is_active"]


class GuessBuildingSerializer(serializers.ModelSerializer):
    score = serializers.FloatField(read_only=True)
    sub_scores = serializers.JSONField(read_only=True)
    point = serializers.DictField(source="point_geojson", read_only=True)
    addresses = AddressSerializer(many=True, read_only=True)
    ext_ids = serializers.JSONField(read_only=True)

    class Meta:
        model = Building
        fields = [
            "rnb_id",
            "score",
            "sub_scores",
            "status",
            "point",
            "addresses",
            "ext_ids",
        ]


class BuildingClosestSerializer(serializers.ModelSerializer):
    distance = serializers.SerializerMethodField()
    point = serializers.DictField(source="point_geojson", read_only=True)
    addresses = AddressSerializer(many=True, read_only=True)

    def get_distance(self, obj):
        return obj.distance.m

    class Meta:
        model = Building
        fields = [
            "rnb_id",
            "distance",
            "status",
            "point",
            "addresses",
            "ext_ids",
        ]


class BuildingClosestQuerySerializer(serializers.Serializer):
    radius = serializers.FloatField(required=True)
    point = serializers.CharField(required=True)

    def validate_radius(self, value):
        if value < 0:
            raise serializers.ValidationError("Radius must be positive")
        return value

    # todo : si ouverture à usage externe, utiliser une validation du point plus complète. Exemple dispo dans BuildingGuessParams.__validate_point_from_url()
    def validate_point(self, value):
        """
        we expect a 'lat,lng' format
        """
        try:
            lat, lng = value.split(",")
            lat = float(lat)
            lng = float(lng)
            return value
        except:
            raise serializers.ValidationError("Point is not valid, must be 'lat,lng'")


class CityADSSerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ["code_insee", "name"]


# class BdgInAdsSerializer(serializers.ModelSerializer):
#     geometry = serializers.DictField(source="ads_geojson", required=False)
#     rnb_id = serializers.CharField(validators=[ads_validate_rnbid])
#
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.custom_id = None
#
#     class Meta:
#         model = Building
#         fields = ["rnb_id", "geometry"]
#         validators = [BdgInADSValidator()]
#
#     def to_internal_value(self, data):
#         # Keep the custom id
#         custom_id = data.get("custom_id", None)
#         if custom_id:
#             self.custom_id = custom_id
#
#         return super().to_internal_value(data)

# def to_representation(self, instance):
#     ret = super().to_representation(instance)
#
#     if self.custom_id:
#         ret["custom_id"] = self.custom_id
#
#     return ret
#
# def create(self, validated_data):
#     if validated_data.get("rnb_id") == BdgInADS.NEW_STR:
#         geojson = validated_data.pop("ads_geojson")
#
#         geometry = GEOSGeometry(str(geojson))
#
#         if geometry.geom_type == "Point":
#             validated_data["point"] = f"{geometry}"
#
#         if geometry.geom_type == "MultiPolygon":
#             validated_data["shape"] = f"{geometry}"
#             validated_data["point"] = f"{geometry.point_on_surface}"
#
#         validated_data["rnb_id"] = generate_rnb_id()
#         # we may need to add more info here
#         validated_data["event_origin"] = {"source": "ADS"}
#         building = super().create(validated_data)
#         return building
#     elif validated_data.get("rnb_id") == BdgInADS.GUESS_STR:
#         geojson = validated_data.pop("ads_geojson")
#         geometry = GEOSGeometry(str(geojson))
#
#         if geometry.geom_type == "MultiPolygon":
#             validated_data["shape"] = f"{geometry}"
#             validated_data["point"] = f"{geometry.point_on_surface}"
#
#         bdg = self.guess_bdg(geometry)
#         if isinstance(bdg, Building):
#             return bdg
#
#         if bdg is None:
#             validated_data["rnb_id"] = generate_rnb_id()
#             # we may need to add more info here
#             validated_data["event_origin"] = {"source": "ADS"}
#             building = super().create(validated_data)
#             return building
#
#     else:
#         clean_id = clean_rnb_id(validated_data["rnb_id"])
#         bdg = Building.objects.get(rnb_id=clean_id)
#
#         return bdg
#
# def guess_bdg(self, mp: MultiPolygon) -> Optional[Building]:
#     """Try to guess the building from the MultiPolygon"""
#
#     search = BuildingGuess()
#     search.set_params(**{"poly": mp[0]})
#     qs = search.get_queryset()
#     if len(qs) == 1:
#         return qs[0]
#
#     return None


class BuildingsADSSerializer(serializers.ModelSerializer):
    # building = BdgInAdsSerializer()
    rnb_id = RNBIdField(
        validators=[ads_validate_rnbid], required=False, allow_null=True
    )

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
        geo_field = "shape"
        fields = ["rnb_id", "shape", "operation", "creator"]
        validators = [BdgInADSValidator()]

    def create(self, validated_data):
        # bdg_data = validated_data.pop("building")
        # bdg = BdgInAdsSerializer().create(bdg_data)
        return BuildingADS(**validated_data)

    #
    # def update(self, bdg_ads, validated_data):
    #     validated_data.pop("building")
    #     for attr, value in validated_data.items():
    #         setattr(bdg_ads, attr, value)
    #     return bdg_ads


class ADSSerializer(serializers.ModelSerializer):
    file_number = serializers.CharField(
        required=True,
        validators=[
            UniqueValidator(
                queryset=ADS.objects.all(), message="This file number already exists"
            )
        ],
    )
    decided_at = serializers.DateField(required=True, format="%Y-%m-%d")
    buildings_operations = BuildingsADSSerializer(many=True, required=True)

    creator = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._errors = []

    class Meta:
        model = ADS
        fields = [
            "file_number",
            "decided_at",
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

        # Remove all previous operations
        ads.buildings_operations.all().delete()

        # Add new operations
        bdg_ops = []
        if "buildings_operations" in validated_data:
            bdg_ops = validated_data.pop("buildings_operations")

        for bdg_op_data in bdg_ops:
            bdg_op = BuildingsADSSerializer().create(bdg_op_data)
            bdg_op.ads = ads
            bdg_op.save()

        # Update other fields
        for attr, value in validated_data.items():
            setattr(ads, attr, value)
        ads.save()

        return ads

    #
    # def update(self, ads, validated_data):
    #     data_bdg_ops = []
    #     if "buildings_operations" in validated_data:
    #         data_bdg_ops = validated_data.pop("buildings_operations")
    #
    #     for attr, value in validated_data.items():
    #         setattr(ads, attr, value)
    #
    #     ads.save()
    #
    #     if data_bdg_ops:
    #         # First, we remove operations which are in the ADS but not in sent data (matching on RNB ID)
    #         data_rnb_ids = [b["building"]["rnb_id"] for b in data_bdg_ops]
    #         for model_bdg_op in ads.buildings_operations.all():
    #             if model_bdg_op.building.rnb_id not in data_rnb_ids:
    #                 model_bdg_op.delete()
    #
    #         # Then we add the new operations
    #         for data_bdg_op in data_bdg_ops:
    #             # First we check if the building is already in the ADS
    #             adslogic = ADSLogic(ads)
    #             if adslogic.concerns_rnb_id(data_bdg_op["building"]["rnb_id"]):
    #                 bdg_op = adslogic.get_op_by_rnbid(data_bdg_op["building"]["rnb_id"])
    #                 bdg_op = BuildingsADSSerializer().update(bdg_op, data_bdg_op.copy())
    #             else:
    #                 bdg_op = BuildingsADSSerializer().create(data_bdg_op.copy())
    #                 bdg_op.ads = ads
    #             bdg_op.save()
    #
    #     return ads
