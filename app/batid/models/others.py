from zoneinfo import ZoneInfo

import requests
from batid.exceptions import (
    BANAPIDown,
    BANBadRequest,
    BANBadResultType,
    BANUnknownCleInterop,
)
from batid.validators import JSONSchemaValidator
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.contrib.postgres.fields import ArrayField
from django.db.models.functions import TruncDate


class BuildingAddressesReadOnly(models.Model):
    building = models.ForeignKey("Building", on_delete=models.CASCADE, db_index=True)
    address = models.ForeignKey("Address", on_delete=models.CASCADE, db_index=True)

    class Meta:
        unique_together = ("building", "address")


class BuildingValidatedByReadOnly(models.Model):
    building = models.ForeignKey("Building", on_delete=models.PROTECT, db_index=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, db_index=True)

    class Meta:
        unique_together = ("building", "user")


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
    ban_id = models.UUIDField(db_index=True, null=True, blank=True, unique=True)
    # Does the cle d'interop still exists in the BAN?
    # None = not yet checked, True = exists, False = explicitly absent
    still_exists = models.BooleanField(db_index=True, null=True, default=None)
    ban_update_flag = models.CharField(
        max_length=20, null=True, default=None, db_index=True
    )
    ban_update_details = models.JSONField(null=True, default=None)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @staticmethod
    def add_addresses_to_db_if_needed(addresses_id: list[str]) -> None:
        """given a list of "clés d'interopérabilité BAN", we add those addresses to our Address table if they don't exist yet."""
        for address_id in addresses_id:
            Address.add_address_to_db_if_needed(address_id)

    @staticmethod
    def add_address_to_db_if_needed(address_id: str) -> None:
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
    def save_new_address(data: dict):
        if data["type"] != "numero":
            raise BANBadResultType

        Address.objects.create(
            id=data["cleInterop"],
            source="ban",
            point=Point(data["lon"], data["lat"], srid=4326),
            street_number=data["numero"],
            street_rep=data["suffixe"],
            street=data["voie"]["nomVoie"],
            city_name=data["commune"]["nom"],
            city_zipcode=data["codePostal"],
            city_insee_code=data["commune"]["code"],
            # We don't import ban_id for now since it creates duplicates and should be treated globally
            # ban_id=data.get("banId"),
            ban_id=None,
        )


class Organization(models.Model):
    name = models.CharField(max_length=100, null=False)
    short_name = models.CharField(max_length=20, null=True, blank=True)
    managed_cities = ArrayField(models.CharField(max_length=6), null=True, blank=True)
    siren = models.CharField(max_length=9, blank=True, null=True, unique=True)
    email_domain = models.CharField(max_length=255, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from batid.services.organization import link_organization_to_users

        link_organization_to_users(self)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    organization = models.ForeignKey(
        "Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="user_profiles",
    )
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


class ProConnectIdentity(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="pro_connect"
    )
    # sub
    # ID sent by the ID provider, unique for each user and stable over time. We use it to identify the user and link it to their account in the RNB.
    # documentation: https://partenaires.proconnect.gouv.fr/docs/fournisseur-service/donnees_fournies
    sub = models.CharField(max_length=255, unique=True, db_index=True)

    # last_id_token
    # Raw JWT id_token from the last login, kept to pass as id_token_hint during logout
    last_id_token = models.TextField(blank=True)

    # SIRET of the user's employer, provided by Pro Connect in the userinfo claims
    siret = models.CharField(max_length=14, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


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
    # featured on the home page
    is_featured = models.BooleanField(
        default=False, verbose_name="visible sur la home (featured)"
    )
    featured_summary = models.TextField(blank=True)
    # displayed on the website on outils-services/rapprochement
    # if not displayed, still used for the stat page
    is_displayed = models.BooleanField(default=True, verbose_name="visible sur le site")
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
        "validation",
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
            city, dpt = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
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
            city, dpt = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
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
            city, dpt = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
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
            city, dpt = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
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
            city, dpt = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
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
            city, dpt = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
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
            city, dpt = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                user=user,
                action="merge",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()

    @staticmethod
    def score_validation(user, point, rnb_id, event_id):
        if user:
            city, dpt = SummerChallenge.get_areas(point)
            sc = SummerChallenge(
                user=user,
                action="validation",
                city=city,
                department=dpt,
                rnb_id=rnb_id,
                event_id=event_id,
            )
            sc.save()


class Trophy(models.Model):
    label = models.CharField(max_length=50, null=False, db_index=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=False, db_index=True)
    level = models.PositiveIntegerField(null=False)
    level_unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "label", "level"], name="unique_user_label_level"
            )
        ]

    # config of the "validateur" trophy: (number of validations, unlocked level)
    VALIDATEUR_LABEL = "validateur"
    VALIDATEUR_THRESHOLDS = [(10, 1), (100, 2), (500, 3)]

    # "course de fond": consecutive calendar days (Europe/Paris) with at least one
    # validation: (number of consecutive days, unlocked level)
    COURSE_DE_FOND_LABEL = "course_de_fond"
    COURSE_DE_FOND_THRESHOLDS = [(7, 1), (21, 2), (42, 3)]
    PARIS_TZ = ZoneInfo("Europe/Paris")

    # "tour de france": validations in distinct stage cities of the Tour de France
    # 2026. Level 3 requires every stage city, hence the threshold is len(codes).
    # French stage cities only (stages 1-2 and the start of stage 3 are in Spain).
    # Resort finishes are mapped to their host commune (e.g. Le Lioran -> Laveissière,
    # Alpe d'Huez -> Huez). INSEE codes verified via geo.api.gouv.fr.
    TOUR_DE_FRANCE_LABEL = "tour_de_france"
    TOUR_DE_FRANCE_2026_INSEE_CODES: list[str] = [
        "66004",  # Les Angles
        "11069",  # Carcassonne
        "09122",  # Foix
        "65258",  # Lannemezan
        "64445",  # Pau
        "65192",  # Gavarnie-Gèdre
        "40119",  # Hagetmau
        "33063",  # Bordeaux
        "24322",  # Périgueux
        "24037",  # Bergerac
        "19123",  # Malemort
        "19275",  # Ussel
        "15014",  # Aurillac
        "15101",  # Laveissière (Le Lioran)
        "03310",  # Vichy
        "58194",  # Nevers
        "58152",  # Magny-Cours
        "71076",  # Chalon-sur-Saône
        "39198",  # Dole
        "90010",  # Belfort
        "68224",  # Mulhouse
        "68089",  # Fellering (Le Markstein)
        "39097",  # Champagnole
        "74049",  # Brizon (Plateau de Solaison)
        "74119",  # Évian-les-Bains
        "74281",  # Thonon-les-Bains
        "73065",  # Chambéry
        "38563",  # Voiron
        "05096",  # Orcières (Orcières-Merlette)
        "05061",  # Gap
        "38191",  # Huez (L'Alpe d'Huez)
        "38052",  # Le Bourg-d'Oisans
        "78616",  # Thoiry
        "75056",  # Paris
    ]

    # "superv": single transferable badge held by the user with the most validations
    SUPERV_LABEL = "superv"

    @staticmethod
    def check_and_award_all(user):
        """Run every badge check for the user and return the list of newly unlocked
        trophies, each as {"label": ..., "level": ...}. Empty list when nothing new."""
        results = []
        for check in (
            Trophy.check_and_award_validateur,
            Trophy.check_and_award_course_de_fond,
            Trophy.check_and_award_tour_de_france,
            Trophy.check_and_award_superv,
        ):
            trophy = check(user)
            if trophy:
                results.append(trophy)
        return results

    @staticmethod
    def _award_threshold_badge(user, label, thresholds, measure):
        """Award the cumulative levels of a threshold-based badge. `thresholds` is a
        list of (min_measure, level) in ascending order. Creates the not-yet-unlocked
        levels up to the one matching `measure`. Idempotent.

        Returns the highest newly unlocked level as {"label": ..., "level": ...},
        or None when nothing new is unlocked.
        """
        target_level = 0
        for min_measure, level in thresholds:
            if measure >= min_measure:
                target_level = level
        if target_level == 0:
            return None

        current_max = (
            Trophy.objects.filter(user=user, label=label).aggregate(
                m=models.Max("level")
            )["m"]
            or 0
        )
        if target_level <= current_max:
            return None

        newly = None
        for lvl in range(current_max + 1, target_level + 1):
            Trophy.objects.create(user=user, label=label, level=lvl)
            newly = lvl

        return {"label": label, "level": newly}

    @staticmethod
    def check_and_award_validateur(user):
        """Count the user's validations and award the 'validateur' badge by threshold
        (10/100/500 validations -> levels 1/2/3).

        Returns the highest newly unlocked level, or None.
        """
        if not user or not user.is_authenticated:
            return None

        count = SummerChallenge.objects.filter(user=user, action="validation").count()
        return Trophy._award_threshold_badge(
            user, Trophy.VALIDATEUR_LABEL, Trophy.VALIDATEUR_THRESHOLDS, count
        )

    @staticmethod
    def check_and_award_course_de_fond(user):
        """Award the 'course de fond' badge based on the longest streak of consecutive
        calendar days (Europe/Paris) on which the user made at least one validation
        (7/21/42 days -> levels 1/2/3).

        Returns the highest newly unlocked level, or None.
        """
        if not user or not user.is_authenticated:
            return None

        days = (
            SummerChallenge.objects.filter(user=user, action="validation")
            .annotate(day=TruncDate("created_at", tzinfo=Trophy.PARIS_TZ))
            .values_list("day", flat=True)
            .distinct()
        )
        streak = Trophy._longest_consecutive_day_streak(days)
        return Trophy._award_threshold_badge(
            user, Trophy.COURSE_DE_FOND_LABEL, Trophy.COURSE_DE_FOND_THRESHOLDS, streak
        )

    @staticmethod
    def _longest_consecutive_day_streak(days):
        """Given an iterable of date objects, return the length of the longest run of
        consecutive calendar days."""
        unique_days = sorted(set(d for d in days if d is not None))
        if not unique_days:
            return 0
        best = run = 1
        for prev, cur in zip(unique_days, unique_days[1:]):
            if (cur - prev).days == 1:
                run += 1
            else:
                run = 1
            best = max(best, run)
        return best

    @staticmethod
    def check_and_award_tour_de_france(user):
        """Award the 'tour de france' badge based on the number of distinct stage cities
        (Tour de France 2026) where the user made a validation (5/15/all -> levels
        1/2/3).

        Returns the highest newly unlocked level, or None.
        """
        if not user or not user.is_authenticated:
            return None

        codes = Trophy.TOUR_DE_FRANCE_2026_INSEE_CODES
        if not codes:
            # not configured yet: never award (avoids awarding level 3 with threshold 0)
            return None

        distinct_cities = (
            SummerChallenge.objects.filter(
                user=user, action="validation", city__code_insee__in=codes
            )
            .values_list("city__code_insee", flat=True)
            .distinct()
            .count()
        )
        thresholds = [(5, 1), (15, 2), (len(codes), 3)]
        return Trophy._award_threshold_badge(
            user, Trophy.TOUR_DE_FRANCE_LABEL, thresholds, distinct_cities
        )

    @staticmethod
    def check_and_award_superv(user):
        """Single, transferable badge held by the user with the most validations. When
        `user` becomes the (sole) leader, the unique 'superv' row is reassigned to them.

        Returns {"label": "superv", "level": 1} when `user` newly takes the lead, else
        None (including when they already held it).
        """
        if not user or not user.is_authenticated:
            return None

        top = (
            SummerChallenge.objects.filter(action="validation")
            .values("user")
            .annotate(c=models.Count("id"))
            .order_by("-c")
            .first()
        )
        if not top or top["user"] != user.id:
            return None

        holder = Trophy.objects.filter(label=Trophy.SUPERV_LABEL).first()
        if holder and holder.user_id == user.id:
            return None

        # transfer the unique badge to the new leader (keep a single row)
        Trophy.objects.filter(label=Trophy.SUPERV_LABEL).delete()
        Trophy.objects.create(user=user, label=Trophy.SUPERV_LABEL, level=1)
        return {"label": Trophy.SUPERV_LABEL, "level": 1}
