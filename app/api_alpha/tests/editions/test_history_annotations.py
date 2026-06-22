import uuid

from batid.models import Building, EditionAnnotation
from batid.tests.factories.users import ReviewerUserFactory
from batid.tests.helpers import coords_to_mp_geom
from rest_framework.test import APITestCase

# A building located in Grenoble
GRENOBLE_COORDS = [
    [5.717918517856731, 45.178820091145724],
    [5.718008279271032, 45.17865980057857],
    [5.7184092135875915, 45.17866401875747],
    [5.7184451181529425, 45.17884961830637],
    [5.717924501950705, 45.17893819969589],
    [5.717918517856731, 45.178820091145724],
]


def create_bdg_with_event_id(rnb_id, event_id):
    """Create a building carrying event_id in a single version (one creation event)."""
    geom = coords_to_mp_geom(GRENOBLE_COORDS)
    return Building.objects.create(
        rnb_id=rnb_id,
        shape=geom,
        point=geom.point_on_surface,
        event_type="creation",
        event_id=event_id,
    )


class BuildingHistoryAnnotationsTest(APITestCase):
    def test_history_exposes_annotations(self):
        """
        Input: a building whose creation event is annotated by a reviewer, then a GET on
        the public building history endpoint.
        Expected: the annotated event carries an "annotations" list filled with the
        reviewer's annotation.
        """
        rnb_id = "AAAA1111BBBB"
        event_id = uuid.uuid4()
        create_bdg_with_event_id(rnb_id, event_id)

        reviewer = ReviewerUserFactory(username="reviewer_1")
        annotation = EditionAnnotation.objects.create(
            event_id=event_id,
            reviewer=reviewer,
            status="incorrect",
            comment="not a building",
        )

        # The history endpoint is public, no credentials required
        r = self.client.get(f"/api/alpha/buildings/{rnb_id}/history/")
        self.assertEqual(r.status_code, 200)

        data = r.json()
        self.assertEqual(len(data), 1)
        annotations = data[0]["event"]["annotations"]
        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0]["id"], annotation.id)
        self.assertEqual(annotations[0]["status"], "incorrect")
        self.assertEqual(annotations[0]["comment"], "not a building")
        self.assertEqual(annotations[0]["reviewer"]["id"], reviewer.id)

    def test_history_without_annotation_returns_empty_list(self):
        """
        Input: a building with no annotation on its events, GET on the history endpoint.
        Expected: each event exposes an empty "annotations" list.
        """
        rnb_id = "CCCC2222DDDD"
        create_bdg_with_event_id(rnb_id, uuid.uuid4())

        r = self.client.get(f"/api/alpha/buildings/{rnb_id}/history/")
        self.assertEqual(r.status_code, 200)

        data = r.json()
        self.assertEqual(data[0]["event"]["annotations"], [])
