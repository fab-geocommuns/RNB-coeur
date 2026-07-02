from dataclasses import dataclass
from zoneinfo import ZoneInfo

from batid.models.others import SummerChallenge
from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.db.models.functions import TruncDate


@dataclass(frozen=True)
class LevelDef:
    """One level of a trophy.

    `threshold` is the minimum measure to unlock the level (None for a single-level
    badge such as 'superv'); `label` is the human-readable level name (None when the
    trophy has a single, unnamed level); `condition` is the human-readable unlock
    condition. `label` and `condition` are exposed by the trophies endpoint.
    """

    level: int
    threshold: int | None
    label: str | None
    condition: str


@dataclass(frozen=True)
class TrophyDef:
    """Full definition of a trophy: `trophy_type` is the identifier stored in the
    ``Trophy.trophy_type`` column, `label` is the display name, plus its `description`
    and its ordered `levels`. Single source of truth for everything the trophies
    endpoints expose and for the award thresholds."""

    trophy_type: str
    label: str
    description: str
    levels: list[LevelDef]

    def get_level(self, level: int) -> LevelDef | None:
        """Return the LevelDef for `level`, or None when the trophy has no such level."""
        return next((lvl for lvl in self.levels if lvl.level == level), None)

    @property
    def thresholds(self) -> list[tuple[int, int]]:
        """The ``(min_measure, level)`` pairs consumed by the threshold-based award
        logic, in ascending order. Levels without a numeric threshold are excluded."""
        return [
            (lvl.threshold, lvl.level)
            for lvl in self.levels
            if lvl.threshold is not None
        ]


class Trophy(models.Model):
    """
    Each row represents of trophy won by a user, with the corresponding timestamp and the
    trophy level.
    """

    trophy_type = models.CharField(max_length=50, null=False, db_index=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=False, db_index=True)
    level = models.PositiveIntegerField(null=False)
    level_unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "trophy_type", "level"],
                name="unique_user_trophy_type_level",
            )
        ]

    PARIS_TZ = ZoneInfo("Europe/Paris")

    # Values stored in the `trophy_type` column, one per trophy.
    VALIDATEUR = "validateur"
    # "course de fond" counts consecutive calendar days (Europe/Paris) with at least
    # one validation.
    COURSE_DE_FOND = "course_de_fond"
    # "tour de france" counts validations in distinct stage cities of the Tour de
    # France 2026.
    TOUR_DE_FRANCE = "tour_de_france"
    # "superv": single transferable badge held by the user with the most validations.
    SUPERV = "superv"

    # Stage cities of the Tour de France 2026. The last "tour de france" level requires
    # every stage city, hence its threshold tracks the length of this list.
    # French stage cities only (stages 1-2 and the start of stage 3 are in Spain).
    # Resort finishes are mapped to their host commune (e.g. Le Lioran -> Laveissière,
    # Alpe d'Huez -> Huez). INSEE codes verified via geo.api.gouv.fr.
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

    # The registry: one TrophyDef per trophy, each carrying every piece of information
    # the trophies endpoints expose (name, description, per-level names and conditions)
    # and the numeric thresholds used to award it. Single source of truth — adding a
    # trophy or a level means editing one place. Order is the display order.
    TROPHY_DEFS = [
        TrophyDef(
            trophy_type=VALIDATEUR,
            label="validateur",
            description=(
                "Gagnez ce trophée en validant des bâtiments dans le RNB. Plus vous "
                "validez, plus votre niveau augmente."
            ),
            levels=[
                LevelDef(
                    level=1,
                    threshold=10,
                    label="apprenti",
                    condition="Valider 10 bâtiments",
                ),
                LevelDef(
                    level=2,
                    threshold=100,
                    label="maçon",
                    condition="Valider 100 bâtiments",
                ),
                LevelDef(
                    level=3,
                    threshold=500,
                    label="entreprise du bâtiment",
                    condition="Valider 500 bâtiments",
                ),
            ],
        ),
        TrophyDef(
            trophy_type=COURSE_DE_FOND,
            label="course de fond",
            description=(
                "Gagnez ce trophée en validant des bâtiments pendant plusieurs jours consécutifs."
            ),
            levels=[
                LevelDef(
                    level=1,
                    threshold=7,
                    label="coureur du dimanche",
                    condition="Valider des bâtiments 7 jours d'affilée",
                ),
                LevelDef(
                    level=2,
                    threshold=21,
                    label="semi-marathonien",
                    condition="Valider des bâtiments 21 jours d'affilée",
                ),
                LevelDef(
                    level=3,
                    threshold=42,
                    label="marathonien",
                    condition="Valider des bâtiments 42 jours d'affilée",
                ),
            ],
        ),
        TrophyDef(
            trophy_type=TOUR_DE_FRANCE,
            label="tour de france",
            description=(
                "Gagnez ce trophée en validant des bâtiments dans les villes-étapes du "
                "Tour de France 2026."
            ),
            # The last level's threshold is recomputed at award time from the code list
            # (see check_and_award_tour_de_france); the value below matches len(codes).
            levels=[
                LevelDef(
                    level=1,
                    threshold=5,
                    label="vainqueur d'étape",
                    condition="Valider des bâtiments dans 5 villes-étapes du Tour de France 2026",
                ),
                LevelDef(
                    level=2,
                    threshold=15,
                    label="maillot jaune",
                    condition="Valider des bâtiments dans 15 villes-étapes du Tour de France 2026",
                ),
                LevelDef(
                    level=3,
                    threshold=len(TOUR_DE_FRANCE_2026_INSEE_CODES),
                    label="vainqueur du tour",
                    condition="Valider des bâtiments dans toutes les villes-étapes du Tour de France 2026",
                ),
            ],
        ),
        TrophyDef(
            trophy_type=SUPERV,
            label="superV",
            description=(
                "Gagnez ce trophée en étant la personne qui a fait le plus de validation "
                "dans le RNB."
            ),
            levels=[
                LevelDef(
                    level=1,
                    threshold=None,
                    label=None,
                    condition="Trophée unique : être la personne ayant réalisé le plus de validations dans le RNB... et le rester",
                ),
            ],
        ),
    ]

    # Lookup by stored trophy_type, e.g. Trophy.TROPHIES["validateur"].
    TROPHIES = {t.trophy_type: t for t in TROPHY_DEFS}

    @classmethod
    def trophy_label(cls, trophy_type):
        """Return the human-readable name of a trophy, or None when undefined."""
        trophy = cls.TROPHIES.get(trophy_type)
        return trophy.label if trophy else None

    @classmethod
    def level_label(cls, trophy_type, level):
        """Return the human-readable name of a (trophy_type, level) pair, or None when
        no name is defined."""
        trophy = cls.TROPHIES.get(trophy_type)
        lvl = trophy.get_level(level) if trophy else None
        return lvl.label if lvl else None

    @staticmethod
    def check_and_award_all(user):
        """Run every badge check for the user and return the list of newly unlocked
        trophies, each as {"trophy_type": ..., "level": ...}. Empty list when nothing
        new."""
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
    def _award_threshold_badge(user, trophy_type, thresholds, measure):
        """Award the cumulative levels of a threshold-based badge. `thresholds` is a
        list of (min_measure, level) in ascending order. Creates the not-yet-unlocked
        levels up to the one matching `measure`. Idempotent.

        Returns the highest newly unlocked level as {"trophy_type": ..., "level": ...},
        or None when nothing new is unlocked.
        """
        target_level = 0
        for min_measure, level in thresholds:
            if measure >= min_measure:
                target_level = level
        if target_level == 0:
            return None

        current_max = (
            Trophy.objects.filter(user=user, trophy_type=trophy_type).aggregate(
                m=models.Max("level")
            )["m"]
            or 0
        )
        if target_level <= current_max:
            return None

        newly = None
        for lvl in range(current_max + 1, target_level + 1):
            Trophy.objects.create(user=user, trophy_type=trophy_type, level=lvl)
            newly = lvl

        return {"trophy_type": trophy_type, "level": newly}

    @staticmethod
    def check_and_award_validateur(user):
        """Count the user's validations and award the 'validateur' badge by threshold
        (10/100/500 validations -> levels 1/2/3).

        Returns the highest newly unlocked level, or None.
        """
        if not user or not user.is_authenticated:
            return None

        count = SummerChallenge.objects.filter(user=user, action="validation").count()
        validateur = Trophy.TROPHIES[Trophy.VALIDATEUR]
        return Trophy._award_threshold_badge(
            user, validateur.trophy_type, validateur.thresholds, count
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
        course_de_fond = Trophy.TROPHIES[Trophy.COURSE_DE_FOND]
        return Trophy._award_threshold_badge(
            user, course_de_fond.trophy_type, course_de_fond.thresholds, streak
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

        distinct_cities = (
            SummerChallenge.objects.filter(
                user=user, action="validation", city__code_insee__in=codes
            )
            .values_list("city__code_insee", flat=True)
            .distinct()
            .count()
        )
        # The last level requires every stage city, so read its threshold from the code
        # list at call time (tests patch it); lower levels keep the definition's values.
        tdf = Trophy.TROPHIES[Trophy.TOUR_DE_FRANCE]
        thresholds = tdf.thresholds[:-1] + [(len(codes), tdf.levels[-1].level)]
        return Trophy._award_threshold_badge(
            user, tdf.trophy_type, thresholds, distinct_cities
        )

    @staticmethod
    def check_and_award_superv(user):
        """Single, transferable badge held by the user with the most validations. When
        `user` becomes the (sole) leader, the unique 'superv' row is reassigned to them.

        Returns {"trophy_type": "superv", "level": 1} when `user` newly takes the lead,
        else None (including when they already held it).
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

        holder = Trophy.objects.filter(trophy_type=Trophy.SUPERV).first()
        if holder and holder.user_id == user.id:
            return None

        # transfer the unique badge to the new leader (keep a single row)
        Trophy.objects.filter(trophy_type=Trophy.SUPERV).delete()
        Trophy.objects.create(user=user, trophy_type=Trophy.SUPERV, level=1)
        return {"trophy_type": Trophy.SUPERV, "level": 1}
