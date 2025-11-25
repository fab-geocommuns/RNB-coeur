import json
from unittest import mock

from django.contrib.auth.models import Group
from django.contrib.gis.geos import GEOSGeometry
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from api_alpha.permissions import RNBContributorPermission
from api_alpha.tests.utils import coordinates_almost_equal
from batid.models import Address
from batid.models import Building
from batid.models import Contribution
from batid.models import Plot
from batid.models import User


class BuildingPlotViewTest(APITestCase):
    def test_buildings_on_plot(self):
        Plot.objects.create(
            id="plot_1", shape="MULTIPOLYGON(((0 0, 0 1, 1 1, 1 0, 0 0)))"
        )
        Plot.objects.create(
            id="plot_2", shape="MULTIPOLYGON(((1 1, 1 2, 2 2, 2 1, 1 1)))"
        )

        # inside plot 1
        building_1 = Building.objects.create(
            rnb_id="building_1",
            shape="POLYGON((0 0, 0 0.5, 0.5 0.5, 0.5 0, 0 0))",
            status="demolished",
        )
        building_1.point = building_1.shape.point_on_surface
        building_1.save()
        # inside plot 1 but inactive
        building_2 = Building.objects.create(
            rnb_id="building_2",
            shape="POLYGON((0 0, 0 0.5, 0.5 0.5, 0.5 0, 0 0))",
            is_active=False,
        )
        building_2.point = building_2.shape.point_on_surface
        building_2.save()

        # # partially on plot_1 and plot_2
        building_3 = Building.objects.create(
            rnb_id="building_3",
            shape="POLYGON((0.5 0.5, 0.5 1.5, 1.5 1.5, 1.5 0.5, 0.5 0.5))",
            is_active=True,
        )
        building_3.point = building_3.shape.point_on_surface
        building_3.save()

        # # plot_1 and plot_2 are completely inside building_4 and _5
        building_4 = Building.objects.create(
            rnb_id="building_4", shape="POLYGON((0 0, 0 2, 2 2, 2 0, 0 0))"
        )
        building_4.point = building_4.shape.point_on_surface
        building_4.save()
        # (but this one is inactive)
        building_5 = Building.objects.create(
            rnb_id="building_5",
            shape="POLYGON((0 0, 0 2, 2 2, 2 0, 0 0))",
            is_active=False,
        )
        building_5.point = building_5.shape.point_on_surface
        building_5.save()

        # building_6 is a point
        building_6 = Building.objects.create(
            rnb_id="building_6", shape="POINT(0.5 0.5)", point="POINT(0.5 0.5)"
        )

        r = self.client.get("/api/alpha/buildings/plot/plot_1/")
        self.assertEqual(r.status_code, 200)
        data = r.json()

        [r1, r2, r3, r4] = data["results"]
        self.assertEqual(r1["rnb_id"], building_1.rnb_id)
        # building_1 is 100% included in the plot
        self.assertEqual(r1["bdg_cover_ratio"], 1.0)

        self.assertEqual(r2["rnb_id"], building_6.rnb_id)
        # building_6 is 100% included in the plot, it's a point!
        self.assertEqual(r1["bdg_cover_ratio"], 1.0)

        self.assertEqual(r3["rnb_id"], building_3.rnb_id)
        # building_3 is 25% included in the plot
        self.assertEqual(r3["bdg_cover_ratio"], 0.25)

        self.assertEqual(r4["rnb_id"], building_4.rnb_id)
        # building_4 is 25% included in the plot
        self.assertEqual(r4["bdg_cover_ratio"], 0.25)

        r = self.client.get("/api/alpha/buildings/plot/plot_2/")
        self.assertEqual(r.status_code, 200)
        data = r.json()

        [r1, r2] = data["results"]
        self.assertEqual(r1["rnb_id"], building_3.rnb_id)
        # building_1 is 100% included in the plot
        self.assertEqual(r1["bdg_cover_ratio"], 0.25)

        self.assertEqual(r2["rnb_id"], building_4.rnb_id)
        # building_3 is 25% included in the plot
        self.assertEqual(r2["bdg_cover_ratio"], 0.25)

    def test_buildings_on_unknown_plot(self):
        r = self.client.get("/api/alpha/buildings/plot/coucou/")
        self.assertEqual(r.status_code, 404)
        res = r.json()
        self.assertEqual(res["detail"], "Plot unknown")
