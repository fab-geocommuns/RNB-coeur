from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from api_alpha.services import BuildingADS as BuildingADSLogic
from api_alpha.services import can_manage_ads_in_request
from api_alpha.validators import ads_validate_rnbid
from api_alpha.validators import ADSValidator
from api_alpha.validators import bdg_is_active
from api_alpha.validators import BdgInADSValidator
from batid.models import Address
from batid.models import ADS
from batid.models import Building
from batid.models import BuildingADS
from batid.models import Contribution
from batid.services.bdg_status import BuildingStatus
from batid.services.rnb_id import clean_rnb_id


class RNBIdField(serializers.CharField):
    def to_internal_value(self, data):
        return clean_rnb_id(data)


class ContributionSerializer(serializers.ModelSerializer):

    # Add a validator to check if the building is active
    rnb_id = serializers.CharField(validators=[bdg_is_active])

    class Meta:
        model = Contribution
        fields = ["rnb_id", "text", "email"]


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id",
            "source",
            "street_number",
            "street_rep",
            "street",
            "city_name",
            "city_zipcode",
            "city_insee_code",
        ]
        extra_kwargs = {
            "id": {"help_text": "02191_0020_00003"},
            "source": {"help_text": "bdnb"},
            "street_number": {"help_text": "3"},
            "street_rep": {"help_text": ""},
            "street": {"help_text": "rue de l'eglise"},
            "city_name": {"help_text": "Chivy-lès-Étouvelles"},
            "city_zipcode": {"help_text": "02000"},
            "city_insee_code": {"help_text": "02191"},
        }


class ExtIdSerializer(serializers.Serializer):
    id = serializers.CharField(help_text="bdnb-bc-3B85-TYM9-FDSX")
    source = serializers.CharField(help_text="bdnb")
    created_at = serializers.DateTimeField(help_text="2023-12-07T13:20:58.310444+00:00")
    source_version = serializers.CharField(help_text="2023_01")


class BuildingSerializer(serializers.ModelSerializer):
    point = serializers.DictField(
        source="point_geojson",
        read_only=True,
        help_text="""{
                            "type": "Point",
                            "coordinates": [
                                3.584410393780201,
                                49.52799819019749
                            ]
                        }""",
    )
    shape = serializers.DictField(
        source="shape_geojson",
        read_only=True,
        help_text="""{
                            "type": "Polygon",
                            "coordinates": [[
                                [100.0, 0.0], [101.0, 0.0], [101.0, 1.0],
                                [100.0, 1.0], [100.0, 0.0]
                             ]]
                        }""",
    )
    addresses = AddressSerializer(
        many=True, read_only=True, source="addresses_read_only"
    )
    ext_ids = ExtIdSerializer(many=True, read_only=True)

    class Meta:
        model = Building
        fields = [
            "rnb_id",
            "status",
            "point",
            "shape",
            "addresses",
            "ext_ids",
            "is_active",
        ]
        extra_kwargs = {
            "rnb_id": {"help_text": "QBAAG16VCJWA"},
            "status": {"help_text": "constructed"},
            "is_active": {"help_text": "true"},
        }


class GuessBuildingSerializer(serializers.ModelSerializer):
    score = serializers.FloatField(read_only=True)
    sub_scores = serializers.JSONField(read_only=True)
    point = serializers.DictField(source="point_geojson", read_only=True)
    addresses = AddressSerializer(
        many=True, read_only=True, source="addresses_read_only"
    )
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
    addresses = AddressSerializer(
        many=True, read_only=True, source="addresses_read_only"
    )

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


class BuildingUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=False)
    status = serializers.ChoiceField(
        choices=BuildingStatus.ALL_TYPES_KEYS, required=False
    )
    addresses_cle_interop = serializers.ListField(
        child=serializers.CharField(min_length=5, max_length=30),
        allow_empty=True,
        required=False,
    )
    comment = serializers.CharField(min_length=4, required=True)

    def validate(self, data):
        if data.get("is_active") is not None and (
            data.get("status") is not None
            or data.get("addresses_cle_interop") is not None
        ):
            raise serializers.ValidationError(
                "you need to either set is_active or set status/addresses, not both at the same time"
            )
        if (
            data.get("is_active") is None
            and data.get("status") is None
            and data.get("addresses_cle_interop") is None
        ):
            raise serializers.ValidationError("empty arguments in the request body")

        return data


class BuildingsADSSerializer(serializers.ModelSerializer):
    # building = BdgInAdsSerializer()
    rnb_id = RNBIdField(
        validators=[ads_validate_rnbid],
        required=False,
        allow_null=True,
        help_text="A1B2C3A1B2C3",
    )

    operation = serializers.ChoiceField(
        required=True,
        choices=BuildingADSLogic.OPERATIONS,
        error_messages={
            "invalid_choice": "'{input}' is not a valid operation. Valid operations are: "
            + f"{BuildingADSLogic.OPERATIONS}."
        },
        help_text="build",
    )

    class Meta:
        model = BuildingADS
        geo_field = "shape"
        fields = ["rnb_id", "shape", "operation"]
        validators = [BdgInADSValidator()]

        extra_kwargs = {
            "rnb_id": {"help_text": "A1B2C3A1B2C3"},
            "shape": {
                "help_text": """{
                                        "type": "Point",
                                        "coordinates": [
                                            5.722961565015281,
                                            45.1851103238598
                                        ]
                                    }"""
            },
            "operation": {"help_text": "demolish"},
        }

    def create(self, validated_data):
        return BuildingADS(**validated_data)


class ADSSerializer(serializers.ModelSerializer):
    file_number = serializers.CharField(
        required=True,
        help_text="TEST03818519U9999",
        validators=[
            UniqueValidator(
                queryset=ADS.objects.all(), message="This file number already exists"
            )
        ],
    )
    decided_at = serializers.DateField(
        required=True, format="%Y-%m-%d", help_text="2023-06-01"
    )
    buildings_operations = BuildingsADSSerializer(many=True, required=True)

    creator = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def is_valid(self, *, raise_exception=False):

        # We have to override the DRF is_valid method to add an extra layer of validation using the request user
        valid = super().is_valid(raise_exception=raise_exception)

        # The extra layer to check if the user can apply the request data
        user = self.context.get("request").user
        if not can_manage_ads_in_request(user, self.initial_data):
            raise serializers.ValidationError(
                {
                    "buildings_operations": "You are not allowed to manage ADS in this city."
                }
            )

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
