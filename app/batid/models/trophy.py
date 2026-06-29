from zoneinfo import ZoneInfo

from batid.models.others import SummerChallenge
from django.contrib.auth.models import User
from django.contrib.gis.db import models
from django.db.models.functions import TruncDate


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

    # Human-readable name of each trophy, exposed by the trophies endpoint as
    # `trophy_label`. Single source of truth for the trophy display names.
    TROPHY_LABELS = {
        VALIDATEUR_LABEL: "validateur",
        COURSE_DE_FOND_LABEL: "course de fond",
        TOUR_DE_FRANCE_LABEL: "tour de france",
        SUPERV_LABEL: "superV",
    }

    # Human-readable explanation of how to earn each trophy, exposed by the trophies
    # endpoint as `description`. Single source of truth for the trophy descriptions.
    TROPHY_DESCRIPTIONS = {
        VALIDATEUR_LABEL: (
            "Gagnez ce trophée en validant des bâtiments dans le RNB. Plus vous "
            "validez, plus votre niveau augmente."
        ),
        COURSE_DE_FOND_LABEL: (
            "Gagnez ce trophée en validant des bâtiments pendant plusieurs jours consécutifs."
        ),
        TOUR_DE_FRANCE_LABEL: (
            "Gagnez ce trophée en validant des bâtiments dans les villes-étapes du "
            "Tour de France 2026."
        ),
        SUPERV_LABEL: (
            "Gagnez ce trophée en étant la personne qui a fait le plus de validation "
            "dans le RNB."
        ),
    }

    # Human-readable name of each (label, level) pair, exposed by the trophies endpoint
    # as `level_label`. The thresholds above stay numeric; this mapping is the single
    # source of truth for the per-level display names.
    # "superv" has a single level, so it has no per-level name (and is absent here).
    LEVEL_LABELS = {
        VALIDATEUR_LABEL: {
            1: "apprenti",
            2: "maçon",
            3: "entreprise du bâtiment",
        },
        COURSE_DE_FOND_LABEL: {
            1: "coureur du dimanche",
            2: "semi-marathonien",
            3: "marathonien",
        },
        TOUR_DE_FRANCE_LABEL: {
            1: "vainqueur d'étape",
            2: "maillot jaune",
            3: "vainqueur du tour",
        },
    }

    @classmethod
    def trophy_label(cls, label):
        """Return the human-readable name of a trophy, or None when undefined."""
        return cls.TROPHY_LABELS.get(label)

    @classmethod
    def trophy_description(cls, label):
        """Return the explanation of how to earn a trophy, or None when undefined."""
        return cls.TROPHY_DESCRIPTIONS.get(label)

    @classmethod
    def level_label(cls, label, level):
        """Return the human-readable name of a (label, level) pair, or None when no
        name is defined."""
        return cls.LEVEL_LABELS.get(label, {}).get(level)

    @classmethod
    def levels(cls, label):
        """Return the ordered list of levels a trophy can reach. Multi-level trophies
        expose their levels through LEVEL_LABELS; single-level trophies (e.g. 'superv')
        default to [1]."""
        return sorted(cls.LEVEL_LABELS.get(label, {}).keys()) or [1]

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
