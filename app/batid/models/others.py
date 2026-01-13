import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField

from batid.exceptions import BANAPIDown
from batid.exceptions import BANBadRequest
from batid.exceptions import BANBadResultType
from batid.exceptions import BANUnknownCleInterop
from batid.validators import JSONSchemaValidator


class BuildingAddressesReadOnly(models.Model):
    building = models.ForeignKey("Building", on_delete=models.CASCADE, db_index=True)
    address = models.ForeignKey("Address", on_delete=models.CASCADE, db_index=True)

    class Meta:
        unique_together = ("building", "address")


class City(models.Model):
    id = models.AutoField(primary_key=True)
    code_insee = models.CharField(max_length=10, null=False, db_index=True, unique=True)
    name = models.CharField(max_length=200, null=False, db_index=True)
    shape = models.MultiPolygonField(null=True, spatial_index=True, srid=4326)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Department(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=3, null=False, db_index=True, unique=True)
    name = models.CharField(max_length=200, null=False)
    shape = models.MultiPolygonField(null=True, spatial_index=True, srid=4326)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Department_subdivided(models.Model):
    # this model exists for performance reasons
    # it is much faster to query on the shape of a department if it is subdivided
    code = models.CharField(max_length=3, null=False)
    name = models.CharField(max_length=200, null=False)
    shape = models.PolygonField(null=True, spatial_index=True, srid=4326)


class ADSAchievement(models.Model):
    file_number = models.CharField(
        max_length=40, null=False, unique=True, db_index=True
    )
    achieved_at = models.DateField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ADS(models.Model):
    file_number = models.CharField(
        max_length=40, null=False, unique=True, db_index=True
    )
    decided_at = models.DateField(null=True)
    achieved_at = models.DateField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    creator = models.ForeignKey(User, on_delete=models.PROTECT, null=True)

    class Meta:
        ordering = ["decided_at"]
        verbose_name = "ADS"
        verbose_name_plural = "ADS"


class BuildingADS(models.Model):
    # building = models.ForeignKey(Building, on_delete=models.CASCADE)
    rnb_id = models.CharField(max_length=12, null=True)
    shape = models.GeometryField(null=True, srid=4326)
    ads = models.ForeignKey(
        ADS, related_name="buildings_operations", on_delete=models.CASCADE
    )

    operation = models.CharField(max_length=10, null=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("rnb_id", "ads")


class Candidate(models.Model):
    shape = models.GeometryField(null=True, srid=4326, spatial_index=False)
    source = models.CharField(max_length=20, null=False)
    source_version = models.CharField(max_length=20, null=True)
    source_id = models.CharField(max_length=40, null=False)
    address_keys = ArrayField(models.CharField(max_length=40), null=True)
    # information coming from the BDTOPO
    # see https://geoservices.ign.fr/sites/default/files/2021-07/DC_BDTOPO_3-0.pdf
    # Indique qu'il s'agit d'une structure légère, non attachée au sol par l'intermédiaire de fondations, ou d'un
    # bâtiment ou partie de bâtiment ouvert sur au moins un côté.
    is_light = models.BooleanField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    inspected_at = models.DateTimeField(null=True, db_index=True)
    inspection_details = models.JSONField(null=True)
    created_by = models.JSONField(null=True)
    random = models.IntegerField(db_index=True, null=False, default=0)


class Plot(models.Model):
    id = models.CharField(max_length=40, primary_key=True, db_index=True)
    shape = models.MultiPolygonField(null=True, srid=4326)

    source_version = models.CharField(max_length=20, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Address(models.Model):
    id = models.CharField(max_length=40, primary_key=True, db_index=True)
    source = models.CharField(max_length=10, null=False)  # BAN or other origin
    point = models.PointField(null=True, spatial_index=True, srid=4326)
    street_number = models.CharField(max_length=10, null=True)
    street_rep = models.CharField(max_length=100, null=True)
    street = models.CharField(max_length=200, null=True)
    city_name = models.CharField(max_length=100, null=True)
    city_zipcode = models.CharField(max_length=5, null=True)
    city_insee_code = models.CharField(max_length=5, null=True)
    ban_id = models.UUIDField(db_index=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @staticmethod
    def add_addresses_to_db_if_needed(addresses_id):
        """given a list of "clés d'interopérabilité BAN", we add those addresses to our Address table if they don't exist yet."""
        for address_id in addresses_id:
            Address.add_address_to_db_if_needed(address_id)

    @staticmethod
    def add_address_to_db_if_needed(address_id):
        if Address.objects.filter(id=address_id).exists():
            return
        else:
            Address.add_new_address_from_ban_api(address_id)

    @staticmethod
    def add_new_address_from_ban_api(address_id):

        BAN_API_URL = "https://plateforme.adresse.data.gouv.fr/lookup/"

        url = f"{BAN_API_URL}{address_id}"
        r = requests.get(url)

        if r.status_code == 200:
            data = r.json()
            Address.save_new_address(data)
        elif r.status_code == 404:
            raise BANUnknownCleInterop
        elif r.status_code == 400:
            raise BANBadRequest
        else:
            raise BANAPIDown

    @staticmethod
    def save_new_address(data):
        if data["type"] != "numero":
            raise BANBadResultType

        Address.objects.create(
            id=data["cleInterop"],
            source="ban",
            point=f'POINT ({data["lon"]} {data["lat"]})',
            street_number=data["numero"],
            street_rep=data["suffixe"],
            street=data["voie"]["nomVoie"],
            city_name=data["commune"]["nom"],
            city_zipcode=data["codePostal"],
            city_insee_code=data["commune"]["code"],
        )


class Organization(models.Model):
    name = models.CharField(max_length=100, null=False)
    users = models.ManyToManyField(User, related_name="organizations")
    managed_cities = ArrayField(models.CharField(max_length=6), null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    job_title = models.CharField(max_length=255, blank=True, null=True)
    max_allowed_contributions = models.IntegerField(null=False, default=500)
    total_contributions = models.IntegerField(null=False, default=0)

    def check_and_increment_contribution_count(self) -> None:
        from api_alpha.exceptions import TooManyContributions

        if (
            settings.ENVIRONMENT != "sandbox"
            and not self.user.is_staff
            and self.total_contributions >= self.max_allowed_contributions
        ):
            raise TooManyContributions(
                detail=f"{self.user.username} a atteint ou dépassé le nombre maximum de contributions autorisées ({self.max_allowed_contributions}). Veuillez nous contacter à rnb@beta.gouv.fr pour plus d'informations."
            )

        self.total_contributions += 1
        self.save(update_fields=["total_contributions"])


class BuildingImport(models.Model):
    id = models.AutoField(primary_key=True)
    import_source = models.CharField(max_length=20, null=False)
    # the id of the "bulk launch"
    # a bulk launch will typically launch an import on the country and will generate an import for each department
    bulk_launch_uuid = models.UUIDField(null=True)
    departement = models.CharField(max_length=3, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    # number of candidates created by the import
    candidate_created_count = models.IntegerField(null=True)
    # what happened to the candidates
    building_created_count = models.IntegerField(null=True)
    building_updated_count = models.IntegerField(null=True)
    building_refused_count = models.IntegerField(null=True)


class DataFix(models.Model):
    """
    Sometimes we need to fix the data in the RNB.
    We identify a problem, run queries to find the corresponding buildings
    and then fix them.
    """

    # a message explaining the problem and the associated fix
    # the text will be displayed to our users
    # and should be written in French.
    # ex : "Suppression des bâtiments légers importés par erreur"
    text = models.TextField(null=True)
    # the user who created the fix
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)


DIFFUSION_DATABASE_ATTRIBUTES_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
            },
            "description": {
                "type": "string",
            },
        },
        "required": ["name", "description"],
        "additionalProperties": False,
    },
}


class DiffusionDatabase(models.Model):
    display_order = models.FloatField(null=False, default=0)
    name = models.CharField(max_length=255)
    documentation_url = models.URLField(null=True)
    publisher = models.CharField(max_length=255, null=True)
    licence = models.CharField(max_length=255, null=True)
    tags = ArrayField(
        models.CharField(max_length=255), null=False, default=list, blank=True
    )
    description = models.TextField(blank=True)
    image_url = models.URLField(null=True)
    is_featured = models.BooleanField(default=False)
    featured_summary = models.TextField(blank=True)
    attributes = models.JSONField(
        null=False,
        default=list,
        blank=True,
        validators=[JSONSchemaValidator(DIFFUSION_DATABASE_ATTRIBUTES_SCHEMA)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order"]


class KPI(models.Model):
    name = models.CharField(max_length=255, null=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    value = models.FloatField(null=False)
    value_date = models.DateField(null=True)

    class Meta:
        ordering = ["value_date"]
        unique_together = ("name", "value_date")


class SummerChallenge(models.Model):
    score = models.IntegerField(null=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=False, db_index=True)
    rnb_id = models.CharField(max_length=12, null=False, db_index=True)

    ACTIONS = [
        "set_address",
        "update_shape",
        "update_status",
        "creation",
        "merge",
        "split",
        "deactivation",
    ]
    action = models.CharField(
        choices=[(e, e) for e in ACTIONS], max_length=14, null=False, db_index=True
    )
    city = models.ForeignKey(City, on_delete=models.PROTECT, null=True, db_index=True)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, null=True, db_index=True
    )
    event_id = models.UUIDField(null=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @staticmethod
    def get_dpt(point):
        d = Department_subdivided.objects.filter(shape__intersects=point).first()
        return Department.objects.filter(code=d.code).first() if d else None

    @staticmethod
    def get_city(point):
        return City.objects.filter(shape__intersects=point).first()

    @staticmethod
    def get_areas(point):
        if point:
            return (SummerChallenge.get_city(point), SummerChallenge.get_dpt(point))
        else:
            return (None, None)

    @staticmethod
    def score_address(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=3,
                user=user,
                action="set_address",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()

    @staticmethod
    def score_creation(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=2,
                user=user,
                action="creation",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()

    @staticmethod
    def score_shape(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=1,
                user=user,
                action="update_shape",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()

    @staticmethod
    def score_status(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=1,
                user=user,
                action="update_status",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()

    @staticmethod
    def score_deactivation(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=2,
                user=user,
                action="deactivation",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()

    @staticmethod
    def score_split(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=1,
                user=user,
                action="split",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()

    @staticmethod
    def score_merge(user, point, rnb_id, event_id):
        if user:
            (city, dpt) = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                score=1,
                user=user,
                action="merge",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()
