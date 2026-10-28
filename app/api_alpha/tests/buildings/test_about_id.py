from batid.models import (
    Building,
    BuildingImport,
    DataFix,
    Organization,
    UserProfile,
)
from batid.models.building import Event
from batid.tests.factories.users import ContributorUserFactory
from django.contrib.gis.geos import GEOSGeometry
from django.test import override_settings
from rest_framework.test import APITestCase

SQUARE_SIZE = 0.0001
ORIGIN = {"source": "contribution", "contribution_id": 1}


def square(x: int, y: int = 0, width: int = 1) -> GEOSGeometry:
    """A polygon of `width` adjacent squares, starting at the (x, y) square of a grid"""
    min_lon = 2.35 + x * SQUARE_SIZE
    min_lat = 48.85 + y * SQUARE_SIZE
    max_lon = min_lon + width * SQUARE_SIZE
    max_lat = min_lat + SQUARE_SIZE
    return GEOSGeometry(
        f"POLYGON(({min_lon} {min_lat}, {min_lon} {max_lat}, {max_lon} {max_lat}, {max_lon} {min_lat}, {min_lon} {min_lat}))",
        srid=4326,
    )


@override_settings(MAX_BUILDING_AREA=float("inf"))
class BuildingAboutIdTest(APITestCase):
    def setUp(self):
        self.user = ContributorUserFactory(username="ju_sig")
        org = Organization.objects.create(name="Mairie de Dreux", short_name="Dreux")
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.organization = org
        profile.save(update_fields=["organization"])

        self.team_rnb = ContributorUserFactory(username="RNB")
        UserProfile.objects.get_or_create(user=self.team_rnb)

    def _create(self, shape: GEOSGeometry, event_origin: dict = ORIGIN) -> Building:
        return Building.create_new(
            user=self.user,
            event_origin=event_origin,
            status="constructed",
            addresses_cle_interop=[],
            shape=shape,
            ext_ids=[],
        )

    def _merge(self, buildings: list[Building]) -> Building:
        for bdg in buildings:
            bdg.refresh_from_db()
        return Building.merge(
            buildings,
            self.user,
            ORIGIN,
            status="constructed",
            addresses_cle_interop=[],
        )

    def _split(self, building: Building, shapes: list[GEOSGeometry]) -> list[Building]:
        building.refresh_from_db()
        return building.split(
            [
                {"status": "constructed", "addresses_cle_interop": [], "shape": s.wkt}
                for s in shapes
            ],
            self.user,
            ORIGIN,
        )

    def _revert(self, building: Building):
        building.refresh_from_db()
        Event.revert_event(
            {"source": "rollback"}, building.event_id, user_making_revert=self.team_rnb
        )

    def _get(self, rnb_id: str) -> dict:
        r = self.client.get(f"/api/alpha/buildings/{rnb_id}/about_id/")
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_active(self):
        """
        Input: a freshly created building, queried with its dashed RNB ID.
        Expected: the ID is active, has no active children and the response describes
        its creation (status, event type, ISO date with timezone, origin, author).
        """
        bdg = self._create(square(0))
        dashed_id = f"{bdg.rnb_id[:4]}-{bdg.rnb_id[4:8]}-{bdg.rnb_id[8:]}"

        data = self._get(dashed_id)

        self.assertEqual(data["rnb_id"], bdg.rnb_id)
        self.assertTrue(data["is_active"])
        self.assertEqual(data["status"], "constructed")
        self.assertEqual(data["event_type"], "creation")
        self.assertTrue(data["updated_at"].endswith("Z"))
        self.assertEqual(data["event_origin"], {"type": "contribution", "id": 1})
        self.assertEqual(
            data["author"],
            {
                "id": self.user.id,
                "username": "ju_sig",
                "organization_name": "Mairie de Dreux",
                "organization_short_name": "Dreux",
            },
        )
        self.assertEqual(data["active_children"], [])

    def test_merge(self):
        """
        Input: A and B merged into C, A is queried.
        Expected: A is inactive, its last event is the merge and C is its only active child.
        """
        a = self._create(square(0))
        b = self._create(square(1))
        c = self._merge([a, b])

        data = self._get(a.rnb_id)

        self.assertFalse(data["is_active"])
        self.assertEqual(data["event_type"], "merge")
        self.assertEqual(data["active_children"], [c.rnb_id])

    def test_split(self):
        """
        Input: A split into C and D, A is queried.
        Expected: A is inactive, its last event is the split and C, D are its active children.
        """
        a = self._create(square(0, width=2))
        children = self._split(a, [square(0), square(1)])

        data = self._get(a.rnb_id)

        self.assertFalse(data["is_active"])
        self.assertEqual(data["event_type"], "split")
        self.assertEqual(
            data["active_children"], sorted(child.rnb_id for child in children)
        )

    def test_lineage_chain(self):
        """
        Input: A and B merged into C, C and E merged into F, F split into G, H, I. A is queried.
        Expected: the active children are the last descendants G, H, I, and the event
        described is the merge of A, not the last event of the chain.
        """
        a = self._create(square(0))
        b = self._create(square(1))
        e = self._create(square(2))
        c = self._merge([a, b])
        f = self._merge([c, e])
        children = self._split(f, [square(0), square(1), square(2)])

        data = self._get(a.rnb_id)

        self.assertFalse(data["is_active"])
        self.assertEqual(data["event_type"], "merge")
        self.assertEqual(
            data["active_children"], sorted(child.rnb_id for child in children)
        )

    def test_merge_three_parents(self):
        """
        Input: A, B and E merged into C, A is queried.
        Expected: C is the only active child, the co-parents B and E are not returned.
        """
        a = self._create(square(0))
        b = self._create(square(1))
        e = self._create(square(2))
        c = self._merge([a, b, e])

        data = self._get(a.rnb_id)

        self.assertEqual(data["active_children"], [c.rnb_id])

    def test_lineage_two_paths_to_same_descendant(self):
        """
        Input: A split into B and C, then B and C merged into D. A is queried.
        Expected: D, reached through both B and C, is returned only once.
        """
        a = self._create(square(0, width=2))
        b, c = self._split(a, [square(0), square(1)])
        d = self._merge([b, c])

        data = self._get(a.rnb_id)

        self.assertEqual(data["active_children"], [d.rnb_id])

    def test_lineage_with_deactivation(self):
        """
        Input: A split into C and D, then D is deactivated. A is queried.
        Expected: only C is an active child of A.
        """
        a = self._create(square(0, width=2))
        c, d = self._split(a, [square(0), square(1)])
        d.refresh_from_db()
        d.deactivate(self.user, ORIGIN)

        data = self._get(a.rnb_id)

        self.assertEqual(data["active_children"], [c.rnb_id])

    def test_lineage_without_active_descendant(self):
        """
        Input: A and B merged into C, then C is deactivated. A is queried.
        Expected: A is inactive and has no active children left.
        """
        a = self._create(square(0))
        b = self._create(square(1))
        c = self._merge([a, b])
        c.refresh_from_db()
        c.deactivate(self.user, ORIGIN)

        data = self._get(a.rnb_id)

        self.assertFalse(data["is_active"])
        self.assertEqual(data["active_children"], [])

    def test_deactivation(self):
        """
        Input: A is deactivated, A is queried.
        Expected: A is inactive, its last event is the deactivation and it has no active children.
        """
        a = self._create(square(0))
        a.deactivate(self.user, ORIGIN)

        data = self._get(a.rnb_id)

        self.assertFalse(data["is_active"])
        self.assertEqual(data["event_type"], "deactivation")
        self.assertEqual(data["active_children"], [])

    def test_reverted_merge(self):
        """
        Input: A and B merged into C, then the merge is reverted.
        Expected: A is active again with no active children (last event: revert_merge),
        and C leads back to the reactivated A and B.
        """
        a = self._create(square(0))
        b = self._create(square(1))
        c = self._merge([a, b])
        self._revert(c)

        data_a = self._get(a.rnb_id)
        self.assertTrue(data_a["is_active"])
        self.assertEqual(data_a["event_type"], "revert_merge")
        self.assertEqual(data_a["active_children"], [])

        data_c = self._get(c.rnb_id)
        self.assertFalse(data_c["is_active"])
        self.assertEqual(data_c["event_type"], "revert_merge")
        self.assertEqual(data_c["active_children"], sorted([a.rnb_id, b.rnb_id]))

    def test_reverted_split(self):
        """
        Input: A split into C and D, then the split is reverted. C is queried.
        Expected: C is inactive and leads back to the reactivated A.
        """
        a = self._create(square(0, width=2))
        c, d = self._split(a, [square(0), square(1)])
        a.refresh_from_db()
        self._revert(a)

        data = self._get(c.rnb_id)

        self.assertFalse(data["is_active"])
        self.assertEqual(data["event_type"], "revert_split")
        self.assertEqual(data["active_children"], [a.rnb_id])

    def test_reverted_merge_then_split(self):
        """
        Input: A and B merged into C, the merge is reverted, then the reactivated A
        is split into D and E. C is queried.
        Expected: the lineage goes back to A and B, then down to A's split children:
        the active children are B, D and E.
        """
        a = self._create(square(0, width=2))
        b = self._create(square(2))
        c = self._merge([a, b])
        self._revert(c)
        d, e = self._split(a, [square(0), square(1)])

        data = self._get(c.rnb_id)

        self.assertEqual(
            data["active_children"], sorted([b.rnb_id, d.rnb_id, e.rnb_id])
        )

    def test_import_origin(self):
        """
        Input: a building created by an import.
        Expected: the event origin gives the import type and id, and there is no author.
        """
        bdg_import = BuildingImport.objects.create(
            departement="75",
            import_source="bdtopo",
            building_created_count=0,
            building_updated_count=0,
            building_refused_count=0,
            candidate_created_count=0,
        )
        bdg = Building.create_new(
            user=None,
            event_origin={"source": "import", "id": bdg_import.id},
            status="constructed",
            addresses_cle_interop=[],
            shape=square(0),
            ext_ids=[],
        )

        data = self._get(bdg.rnb_id)

        self.assertEqual(data["event_origin"], {"type": "import", "id": bdg_import.id})
        self.assertIsNone(data["author"])

    def test_data_fix_origin(self):
        """
        Input: a building created by a data fix.
        Expected: the event origin gives the data_fix type and id.
        """
        data_fix = DataFix.objects.create(text="Correction de bâtiments")
        bdg = self._create(square(0), {"source": "data_fix", "id": data_fix.id})

        data = self._get(bdg.rnb_id)

        self.assertEqual(data["event_origin"], {"type": "data_fix", "id": data_fix.id})

    def test_unknown_rnb_id(self):
        """
        Input: an RNB ID which does not exist.
        Expected: a 404 error.
        """
        r = self.client.get("/api/alpha/buildings/AAAABBBBCCCC/about_id/")
        self.assertEqual(r.status_code, 404)
