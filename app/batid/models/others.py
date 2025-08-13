from datetime import datetime

import requests
from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField

from batid.exceptions import BANAPIDown
from batid.exceptions import BANBadRequest
from batid.exceptions import BANBadResultType
from batid.exceptions import BANUnknownCleInterop
from batid.validators import JSONSchemaValidator


class BuildingAddressesReadOnly(models.Model):
    building = models.ForeignKey("Building", on_delete=models.CASCADE, db_index=True)  # type: ignore[var-annotated]
    address = models.ForeignKey("Address", on_delete=models.CASCADE, db_index=True)  # type: ignore[var-annotated]

    class Meta:
        unique_together = ("building", "address")


class City(models.Model):
    id = models.AutoField(primary_key=True)  # type: ignore[var-annotated]
    code_insee = models.CharField(max_length=10, null=False, db_index=True, unique=True)  # type: ignore[var-annotated]
    name = models.CharField(max_length=200, null=False, db_index=True)  # type: ignore[var-annotated]
    shape = models.MultiPolygonField(null=True, spatial_index=True, srid=4326)  # type: ignore[var-annotated]
    created_at = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]


class Department(models.Model):
    id = models.AutoField(primary_key=True)  # type: ignore[var-annotated]
    code = models.CharField(max_length=3, null=False, db_index=True, unique=True)  # type: ignore[var-annotated]
    name = models.CharField(max_length=200, null=False)  # type: ignore[var-annotated]
    shape = models.MultiPolygonField(null=True, spatial_index=True, srid=4326)  # type: ignore[var-annotated]
    created_at = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]


class Department_subdivided(models.Model):
    # this model exists for performance reasons
    # it is much faster to query on the shape of a department if it is subdivided
    code = models.CharField(max_length=3, null=False)  # type: ignore[var-annotated]
    name = models.CharField(max_length=200, null=False)  # type: ignore[var-annotated]
    shape = models.PolygonField(null=True, spatial_index=True, srid=4326)  # type: ignore[var-annotated]


class ADSAchievement(models.Model):
    file_number = models.CharField(  # type: ignore[var-annotated]
        max_length=40, null=False, unique=True, db_index=True
    )
    achieved_at = models.DateField(null=True)  # type: ignore[var-annotated]
    created_at = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]


class ADS(models.Model):
    file_number = models.CharField(  # type: ignore[var-annotated]
        max_length=40, null=False, unique=True, db_index=True
    )
    decided_at = models.DateField(null=True)  # type: ignore[var-annotated]
    achieved_at = models.DateField(null=True)  # type: ignore[var-annotated]
    created_at = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]

    creator = models.ForeignKey(User, on_delete=models.PROTECT, null=True)  # type: ignore[var-annotated]

    class Meta:
        ordering = ["decided_at"]
        verbose_name = "ADS"
        verbose_name_plural = "ADS"


class BuildingADS(models.Model):
    # building = models.ForeignKey(Building, on_delete=models.CASCADE)
    rnb_id = models.CharField(max_length=12, null=True)  # type: ignore[var-annotated]
    shape = models.GeometryField(null=True, srid=4326)  # type: ignore[var-annotated]
    ads = models.ForeignKey(  # type: ignore[var-annotated]
        ADS, related_name="buildings_operations", on_delete=models.CASCADE
    )

    operation = models.CharField(max_length=10, null=False)  # type: ignore[var-annotated]
    created_at = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]

    class Meta:
        unique_together = ("rnb_id", "ads")


class Candidate(models.Model):
    shape = models.GeometryField(null=True, srid=4326, spatial_index=False)  # type: ignore[var-annotated]
    source = models.CharField(max_length=20, null=False)  # type: ignore[var-annotated]
    source_version = models.CharField(max_length=20, null=True)  # type: ignore[var-annotated]
    source_id = models.CharField(max_length=40, null=False)  # type: ignore[var-annotated]
    address_keys = ArrayField(models.CharField(max_length=40), null=True)  # type: ignore[var-annotated]
    # information coming from the BDTOPO
    # see https://geoservices.ign.fr/sites/default/files/2021-07/DC_BDTOPO_3-0.pdf
    # Indique qu'il s'agit d'une structure légère, non attachée au sol par l'intermédiaire de fondations, ou d'un
    # bâtiment ou partie de bâtiment ouvert sur au moins un côté.
    is_light = models.BooleanField(null=True)  # type: ignore[var-annotated]

    created_at = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]

    inspected_at = models.DateTimeField(null=True, db_index=True)  # type: ignore[var-annotated]
    inspection_details = models.JSONField(null=True)
    created_by = models.JSONField(null=True)
    random = models.IntegerField(db_index=True, null=False, default=0)  # type: ignore[var-annotated]


class Plot(models.Model):
    id = models.CharField(max_length=40, primary_key=True, db_index=True)  # type: ignore[var-annotated]
    shape = models.MultiPolygonField(null=True, srid=4326)  # type: ignore[var-annotated]

    source_version = models.CharField(max_length=20, null=True)  # type: ignore[var-annotated]

    created_at = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]


class Address(models.Model):
    id = models.CharField(max_length=40, primary_key=True, db_index=True)  # type: ignore[var-annotated]
    source = models.CharField(  # type: ignore[var-annotated]
        max_length=10, null=False
    )  # BAN or other origin
    point = models.PointField(null=True, spatial_index=True, srid=4326)  # type: ignore[var-annotated]
    street_number = models.CharField(max_length=10, null=True)  # type: ignore[var-annotated]
    street_rep = models.CharField(max_length=100, null=True)  # type: ignore[var-annotated]
    street = models.CharField(max_length=200, null=True)  # type: ignore[var-annotated]
    city_name = models.CharField(max_length=100, null=True)  # type: ignore[var-annotated]
    city_zipcode = models.CharField(max_length=5, null=True)  # type: ignore[var-annotated]
    city_insee_code = models.CharField(max_length=5, null=True)  # type: ignore[var-annotated]

    created_at = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]

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
    name = models.CharField(max_length=100, null=False)  # type: ignore[var-annotated]
    users = models.ManyToManyField(User, related_name="organizations")  # type: ignore[var-annotated]
    managed_cities = ArrayField(models.CharField(max_length=6), null=True)  # type: ignore[var-annotated]

    created_at = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")  # type: ignore[var-annotated]
    job_title = models.CharField(max_length=255, blank=True, null=True)  # type: ignore[var-annotated]


class BuildingImport(models.Model):
    id = models.AutoField(primary_key=True)  # type: ignore[var-annotated]
    import_source = models.CharField(max_length=20, null=False)  # type: ignore[var-annotated]
    # the id of the "bulk launch"
    # a bulk launch will typically launch an import on the country and will generate an import for each department
    bulk_launch_uuid = models.UUIDField(null=True)  # type: ignore[var-annotated]
    departement = models.CharField(max_length=3, null=True)  # type: ignore[var-annotated]
    created_at = models.DateTimeField(auto_now_add=True, null=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]
    # number of candidates created by the import
    candidate_created_count = models.IntegerField(null=True)  # type: ignore[var-annotated]
    # what happened to the candidates
    building_created_count = models.IntegerField(null=True)  # type: ignore[var-annotated]
    building_updated_count = models.IntegerField(null=True)  # type: ignore[var-annotated]
    building_refused_count = models.IntegerField(null=True)  # type: ignore[var-annotated]


class Contribution(models.Model):
    id = models.AutoField(primary_key=True)  # type: ignore[var-annotated]
    rnb_id = models.CharField(max_length=255, null=True)  # type: ignore[var-annotated]
    text = models.TextField(null=True)  # type: ignore[var-annotated]
    email = models.EmailField(null=True, blank=True)  # type: ignore[var-annotated]
    created_at = models.DateTimeField(auto_now_add=True, null=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]
    # is it a user report (a modification proposal or "signalement" in French) or a direct data modification?
    report = models.BooleanField(null=False, db_index=True, default=True)  # type: ignore[var-annotated]
    # useful for reports (signalements)
    status = models.CharField(  # type: ignore[var-annotated]
        choices=[("pending", "pending"), ("fixed", "fixed"), ("refused", "refused")],
        max_length=10,
        null=False,
        default="pending",
        db_index=True,
    )
    status_changed_at = models.DateTimeField(null=True, blank=True)  # type: ignore[var-annotated]
    review_comment = models.TextField(null=True, blank=True)  # type: ignore[var-annotated]
    review_user = models.ForeignKey(  # type: ignore[var-annotated]
        User, on_delete=models.PROTECT, null=True, blank=True
    )
    # if an event on a Building (eg a deactivation) updates the status of a "signalement" (eg status set to refused).
    status_updated_by_event_id = models.UUIDField(null=True, db_index=True)  # type: ignore[var-annotated]

    def fix(self, user, review_comment=""):
        if self.status != "pending":
            raise ValueError("Contribution is not pending.")

        self.status = "fixed"
        self.status_changed_at = datetime.now()
        self.review_comment = review_comment
        self.review_user = user
        self.save()

    def refuse(self, user, review_comment="", status_updated_by_event_id=None):
        if self.status != "pending":
            raise ValueError("Contribution is not pending.")

        self.status = "refused"
        self.status_changed_at = datetime.now()
        self.review_comment = review_comment
        self.review_user = user
        self.status_updated_by_event_id = status_updated_by_event_id
        self.save()

    def reset_pending(self):
        """
        A signalement has been refused because its underlying building has been deactivated.
        The building is finally reactivated => we reset the signalement to a pending status.
        """
        self.status = "pending"
        self.status_changed_at = None
        self.review_comment = None
        self.review_user = None
        self.status_updated_by_event_id = None
        self.save()


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
    text = models.TextField(null=True)  # type: ignore[var-annotated]
    # the user who created the fix
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)  # type: ignore[var-annotated]
    created_at = models.DateTimeField(auto_now_add=True, null=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]


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
    display_order = models.FloatField(null=False, default=0)  # type: ignore[var-annotated]
    name = models.CharField(max_length=255)  # type: ignore[var-annotated]
    documentation_url = models.URLField(null=True)  # type: ignore[var-annotated]
    publisher = models.CharField(max_length=255, null=True)  # type: ignore[var-annotated]
    licence = models.CharField(max_length=255, null=True)  # type: ignore[var-annotated]
    tags = ArrayField(  # type: ignore[var-annotated]
        models.CharField(max_length=255), null=False, default=list, blank=True
    )
    description = models.TextField(blank=True)  # type: ignore[var-annotated]
    image_url = models.URLField(null=True)  # type: ignore[var-annotated]
    is_featured = models.BooleanField(default=False)  # type: ignore[var-annotated]
    featured_summary = models.TextField(blank=True)  # type: ignore[var-annotated]
    attributes = models.JSONField(
        null=False,
        default=list,
        blank=True,
        validators=[JSONSchemaValidator(DIFFUSION_DATABASE_ATTRIBUTES_SCHEMA)],
    )
    created_at = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]


class KPI(models.Model):
    name = models.CharField(max_length=255, null=False, db_index=True)  # type: ignore[var-annotated]
    created_at = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]
    value = models.FloatField(null=False)  # type: ignore[var-annotated]
    value_date = models.DateField(null=True)  # type: ignore[var-annotated]

    class Meta:
        ordering = ["value_date"]
        unique_together = ("name", "value_date")


class SummerChallenge(models.Model):
    score = models.IntegerField(null=False)  # type: ignore[var-annotated]
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=False, db_index=True)  # type: ignore[var-annotated]
    rnb_id = models.CharField(max_length=12, null=False, db_index=True)  # type: ignore[var-annotated]

    ACTIONS = [
        "set_address",
        "update_shape",
        "update_status",
        "creation",
        "merge",
        "split",
        "deactivation",
    ]
    action = models.CharField(  # type: ignore[var-annotated]
        choices=[(e, e) for e in ACTIONS], max_length=14, null=False, db_index=True
    )
    city = models.ForeignKey(City, on_delete=models.PROTECT, null=True, db_index=True)  # type: ignore[var-annotated]
    department = models.ForeignKey(  # type: ignore[var-annotated]
        Department, on_delete=models.PROTECT, null=True, db_index=True
    )
    event_id = models.UUIDField(null=False, db_index=True)  # type: ignore[var-annotated]
    created_at = models.DateTimeField(auto_now_add=True)  # type: ignore[var-annotated]
    updated_at = models.DateTimeField(auto_now=True)  # type: ignore[var-annotated]

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
