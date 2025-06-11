import math

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.gis.geos import GEOSGeometry
from django.db import transaction
from rest_framework import serializers
from rest_framework.authtoken.models import Token
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
from batid.models import BuildingWithHistory
from batid.models import BuildingADS
from batid.models import Contribution
from batid.models import DiffusionDatabase
from batid.models import Organization
from batid.models import UserProfile
from batid.services.bdg_status import BuildingStatus
from batid.services.email import build_activate_account_email
from batid.services.rnb_id import clean_rnb_id
from batid.services.user import get_user_id_b64


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


class BuildingHistorySerializer(serializers.Serializer):
    rnb_id = RNBIdField()
    # point = serializers.DictField(
    #     source="point_geojson",
    #     read_only=True,
    # )
    # shape = serializers.DictField(
    #     source="shape_geojson",
    #     read_only=True,
    # )
    # addresses = AddressSerializer(
    #     many=True, read_only=True, source="addresses_read_only"
    # )
    # ext_ids = ExtIdSerializer(many=True, read_only=True)

    class Meta:
        # No model specified, this is a plain Serializer, not a ModelSerializer
        fields = ["rnb_id"]


class BuildingSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):

        # We have to intercept the with_plots arguments before passing to the parent class
        with_plots = kwargs.pop("with_plots", False)

        # Trigger the parent class init
        super().__init__(*args, **kwargs)

        # If with_plots is False, we remove the plots field from the fields list
        if not with_plots:
            self.fields.pop("plots")

    point = serializers.DictField(
        source="point_geojson",
        read_only=True,
    )
    shape = serializers.DictField(
        source="shape_geojson",
        read_only=True,
    )
    addresses = AddressSerializer(
        many=True, read_only=True, source="addresses_read_only"
    )
    ext_ids = ExtIdSerializer(many=True, read_only=True)
    plots = serializers.JSONField(read_only=True)

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
            "plots",
        ]


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
            "shape",
        ]


def validate_point(coords_str: str):
    if not coords_str:
        raise serializers.ValidationError(
            "Le point n'est pas valide, doit être 'lat,lng'"
        )

    coords = coords_str.split(",")

    if len(coords) != 2:
        raise serializers.ValidationError(
            "Le point n'est pas valide, doit être 'lat,lng'"
        )

    try:
        lat = float(coords[0])
    except:
        raise serializers.ValidationError(
            "Le point n'est pas valide car la latitude n'est pas valide"
        )

    try:
        lon = float(coords[1])
    except:
        raise serializers.ValidationError(
            "Le point n'est pas valide car la longitude n'est pas valide"
        )

    if lat < -90 or lat > 90 or math.isnan(lat):
        raise serializers.ValidationError(
            "Le point n'est pas valide, la latitude doit être entre -90 et 90"
        )

    if lon < -180 or lon > 180 or math.isnan(lon):
        raise serializers.ValidationError(
            "Le point n'est pas valide, la longitude doit être entre -180 et 180"
        )


class BuildingClosestQuerySerializer(serializers.Serializer):
    radius = serializers.FloatField(required=True)
    point = serializers.CharField(required=True, validators=[validate_point])

    def validate_radius(self, value):
        if value < 0:
            raise serializers.ValidationError("Le rayon doit être positif")

        if value > 1000:
            raise serializers.ValidationError(
                "Le rayon doit être inférieur à 1000 mètres"
            )

        return value


class BuildingAddressQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False)
    min_score = serializers.FloatField(required=False)
    cle_interop_ban = serializers.CharField(required=False)

    def validate_min_score(self, min_score):
        if min_score < 0 or min_score > 1:
            raise serializers.ValidationError("'min_score' doit être entre 0. et 1.0")
        return min_score

    def validate(self, data):
        # one (and only one) field is required
        if (data.get("q") is None and data.get("cle_interop_ban") is None) or (
            data.get("q") is not None and data.get("cle_interop_ban") is not None
        ):
            raise serializers.ValidationError(
                "Vous devez définir soit 'q' soit 'cle_interop_ban'."
            )

        if data.get("cle_interop_ban") and data.get("min_score"):
            raise serializers.ValidationError(
                "'min_score' n'est pertinent qu'avec une adresse textuelle"
            )

        return data


class BuildingPlotSerializer(serializers.ModelSerializer):
    bdg_cover_ratio = serializers.SerializerMethodField()
    point = serializers.DictField(source="point_geojson", read_only=True)
    addresses = AddressSerializer(
        many=True, read_only=True, source="addresses_read_only"
    )

    def get_bdg_cover_ratio(self, obj):
        return obj.bdg_cover_ratio

    class Meta:
        model = Building
        fields = [
            "rnb_id",
            "bdg_cover_ratio",
            "status",
            "point",
            "addresses",
            "ext_ids",
        ]


def shape_is_valid(shape):
    if shape is None:
        return None

    try:
        g = GEOSGeometry(shape)
        if not g.valid:
            raise Exception
    except:
        raise serializers.ValidationError(
            "La forme fournie n'a pas pu être analysée ou n'est pas valide"
        )
    return shape


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
    shape = serializers.CharField(required=False, validators=[shape_is_valid])
    comment = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        if data.get("is_active") is not None and (
            data.get("status") is not None
            or data.get("addresses_cle_interop") is not None
            or data.get("shape") is not None
        ):
            raise serializers.ValidationError(
                "Vous devez définir soit 'is_active' soit 'status'/'addresses_cle_interop'/'shape', pas les deux en même temps"
            )
        if (
            data.get("is_active") is None
            and data.get("status") is None
            and data.get("addresses_cle_interop") is None
            and data.get("shape") is None
        ):
            raise serializers.ValidationError(
                "Arguments vides dans le corps de la requête"
            )

        return data


class BuildingCreateSerializerCore(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=BuildingStatus.ALL_TYPES_KEYS, required=True
    )
    addresses_cle_interop = serializers.ListField(
        child=serializers.CharField(min_length=5, max_length=30),
        allow_empty=True,
        required=True,
    )
    shape = serializers.CharField(required=True, validators=[shape_is_valid])


class BuildingCreateSerializer(BuildingCreateSerializerCore):
    comment = serializers.CharField(required=False, allow_blank=True)


class BuildingMergeSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True)
    rnb_ids = serializers.ListField(
        child=serializers.CharField(min_length=12, max_length=12),
        min_length=2,
        allow_empty=False,
        required=True,
    )
    merge_existing_addresses = serializers.BooleanField(required=False)
    addresses_cle_interop = serializers.ListField(
        child=serializers.CharField(min_length=5, max_length=30),
        allow_empty=True,
        required=False,
    )
    status = serializers.ChoiceField(
        choices=BuildingStatus.ALL_TYPES_KEYS, required=True
    )

    def validate(self, data):
        if data.get("merge_existing_addresses") and data.get("addresses_cle_interop"):
            raise serializers.ValidationError(
                "Si 'merge_existing_addresses' est défini à True, vous ne pouvez pas spécifier 'addresses_cle_interop'"
            )
        if (
            not data.get("merge_existing_addresses")
            and data.get("addresses_cle_interop") is None
        ):
            raise serializers.ValidationError(
                "'merge_existing_addresses' ou 'addresses_cle_interop' doit être défini"
            )

        return data


class BuildingSplitSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True)
    created_buildings = serializers.ListField(
        min_length=2,
        required=True,
        allow_empty=False,
        child=BuildingCreateSerializerCore(),
    )


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
            "invalid_choice": "'{input}' n'est pas une opération valide. Les opérations valides sont : "
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
                queryset=ADS.objects.all(), message="Ce numéro de dossier existe déjà"
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
                    "buildings_operations": "Vous n'êtes pas autorisé à gérer les ADS dans cette ville."
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


class DiffusionDatabaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiffusionDatabase
        fields = "__all__"


class UserSerializer(serializers.ModelSerializer):
    # this field will never be sent back for security reasons
    password = serializers.CharField(write_only=True)
    job_title = serializers.CharField(source="profile.job_title", required=False)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    email = serializers.CharField(required=True)

    class Meta:
        model = User
        fields = [
            "last_name",
            "first_name",
            "email",
            "username",
            "password",
            "job_title",
        ]

    def validate_email(self, value):
        if (
            User.objects.filter(email=value).exists()
            or User.objects.filter(username=value).exists()
        ):
            raise serializers.ValidationError(
                "Un utilisateur avec cette adresse email existe déjà."
            )
        return value

    def validate_username(self, value):
        if (
            User.objects.filter(email=value).exists()
            or User.objects.filter(username=value).exists()
        ):
            raise serializers.ValidationError("Un utilisateur avec ce nom existe déjà.")
        return value

    def create(self, validated_data):
        profile_data = validated_data.pop("profile", {})

        user = User(
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            username=validated_data["username"],
            email=validated_data["email"],
        )
        user.set_password(validated_data["password"])
        user.is_active = settings.ENVIRONMENT == "sandbox"
        user.save()

        group = Group.objects.get(name=settings.CONTRIBUTORS_GROUP_NAME)
        user.groups.add(group)
        user.save()
        Token.objects.get_or_create(user=user)

        if not user.is_active:
            transaction.on_commit(lambda: send_user_email_with_activation_link(user))

        # add info (job_title) in the User profile
        UserProfile.objects.update_or_create(
            user=user, defaults={"job_title": profile_data.get("job_title")}
        )

        return user


def send_user_email_with_activation_link(user):
    token = default_token_generator.make_token(user)
    user_id_b64 = get_user_id_b64(user)
    email = build_activate_account_email(token, user_id_b64, user.email)
    email.send()


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["name"]
