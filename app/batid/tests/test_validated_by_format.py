import csv
import json

from api_alpha.serializers.public_user import PublicUserSerializer
from batid.models import Building, Organization, UserProfile
from batid.services.bdg_history import get_bdg_history
from batid.services.data_gouv_publication import (
    cleanup_directory,
    create_csv,
    create_directory,
)
from batid.tests.factories.users import ContributorUserFactory
from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.test import TestCase


def get_geom_paris():
    coords = {
        "coordinates": [
            [
                [2.353721421744524, 48.83801408684721],
                [2.3538278210596104, 48.83790774339977],
                [2.353989390389472, 48.83797518073416],
                [2.3538810207165, 48.83809708645475],
                [2.353721421744524, 48.83801408684721],
            ]
        ],
        "type": "Polygon",
    }
    return GEOSGeometry(json.dumps(coords), srid=4326)


class ValidatedByFormatContractTest(TestCase):
    """
    Contrat de format du champ `validated_by`.

    On vérifie que les deux producteurs SQL (l'export data.gouv et le endpoint
    d'historique) sortent le même format d'objet utilisateur que la référence
    canonique, `PublicUserSerializer`, utilisée par l'API REST.

    Entrée : un bâtiment validé par 3 utilisateurs aux profils variés :
      - un avec organisation (prénom + nom),
      - un sans organisation (prénom + nom),
      - un sans prénom ni nom (déclenche le repli sur `username` côté serializer).

    Deux niveaux de vérification :
      - clés : chaque objet a exactement le jeu de clés du serializer ;
      - valeurs strictes : chaque objet est identique à celui du serializer.

    Si nous faisons évoluer `PublicUserSerializer`, ces tests nous rappelerons
    d'également mettre à jour les requêtes SQL de l'export et du endpoint d'historique.

    """

    def setUp(self):
        # Validateur avec organisation
        self.user_org = ContributorUserFactory(
            first_name="El",
            last_name="Validator",
            username="el_validator",
        )
        org = Organization.objects.create(name="Comité de validation")
        profile, _ = UserProfile.objects.get_or_create(user=self.user_org)
        profile.organization = org
        profile.save(update_fields=["organization"])

        # Validateur sans organisation
        self.user_no_org = ContributorUserFactory(
            first_name="Jean",
            last_name="Doux",
            username="jean_doux",
        )

        # Validateur sans prénom ni nom : le serializer doit retomber sur le username
        self.user_anon = ContributorUserFactory(
            first_name="",
            last_name="",
            username="anon_user",
        )

        self.validators = [self.user_org, self.user_no_org, self.user_anon]

        geom = get_geom_paris()
        self.building = Building.objects.create(
            rnb_id="BDG-CONTRACT",
            shape=geom,
            point=geom.point_on_surface,
            status="constructed",
            ext_ids={"some_source": "1234"},
            is_active=True,
            validated_by=[u.id for u in self.validators],
        )

    def _reference(self):
        # Le serializer de l'API REST fait foi sur le format attendu. On
        # recharge les utilisateurs depuis la base (comme le fait l'API à
        # chaque requête) pour ne pas lire un profil mis en cache par la factory.
        users = list(User.objects.filter(id__in=[u.id for u in self.validators]))
        data = PublicUserSerializer(users, many=True).data
        return sorted((dict(o) for o in data), key=lambda o: o["id"])

    def _export_validated_by(self):
        directory_name = create_directory("nat")
        try:
            create_csv(directory_name, "nat")
            with open(f"{directory_name}/RNB_nat.csv", "r") as f:
                reader = csv.DictReader(f, delimiter=";")
                row = next(r for r in reader if r["rnb_id"] == "BDG-CONTRACT")
                validated_by = json.loads(row["validated_by"])
        finally:
            cleanup_directory(directory_name)
        return sorted(validated_by, key=lambda o: o["id"])

    def _history_validated_by(self):
        history = get_bdg_history("BDG-CONTRACT")
        validated_by = history[0]["validated_by"]
        if isinstance(validated_by, str):
            validated_by = json.loads(validated_by)
        return sorted(validated_by, key=lambda o: o["id"])

    # --- Niveau clés -------------------------------------------------------

    def test_export_keys_match_serializer(self):
        reference = self._reference()
        produced = self._export_validated_by()

        expected_keys = [set(o.keys()) for o in reference]
        self.assertEqual([set(o.keys()) for o in produced], expected_keys)

    def test_history_keys_match_serializer(self):
        reference = self._reference()
        produced = self._history_validated_by()

        expected_keys = [set(o.keys()) for o in reference]
        self.assertEqual([set(o.keys()) for o in produced], expected_keys)

    # --- Niveau valeurs strictes ------------------------------------------

    def test_export_values_match_serializer(self):
        self.assertEqual(self._export_validated_by(), self._reference())

    def test_history_values_match_serializer(self):
        self.assertEqual(self._history_validated_by(), self._reference())
