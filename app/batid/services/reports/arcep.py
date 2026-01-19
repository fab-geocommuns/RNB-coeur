import uuid
from batid.models.report import Report
from batid.models.building import Building
from batid.services.RNB_team_user import get_RNB_team_user
from batid.services.bdg_status import BuildingStatus
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models import functions
from django.contrib.gis.db import models
import csv

ARCEP_TAG_NAME = "Nouveau bâtiment"


def dl_and_create_arcep_reports() -> uuid.UUID:
    from batid.services.source import Source

    source = Source("arcep")
    source.download()

    points = []

    with open(source.find(source.filename), "r") as f:

        reader = csv.DictReader(f)

        for line in reader:

            try:
                lat = float(line["latitude"])
                lng = float(line["longitude"])
                point = Point(lng, lat, srid=4326)
                points.append(point)
            except ValueError:
                raise ValueError(
                    f"Invalid lat/lng values: {line['latitude']}, {line['longitude']}"
                )
    return create_reports(points)


def create_reports(points: list[Point]) -> uuid.UUID:
    creation_uuid = uuid.uuid4()
    team_rnb = get_RNB_team_user()
    tags = [ARCEP_TAG_NAME]

    text = "Un opérateur Internet indique qu'un nouveau bâtiment a été construit ici entre le 01/01/2023 et le 31/12/2025. Faut-il ajouter un nouveau bâtiment au RNB ?"

    for point in points:
        # Check if a real building exists in a 10 meters radius
        if (
            Building.objects.filter(
                is_active=True, status__in=BuildingStatus.REAL_BUILDINGS_STATUS
            )
            .annotate(
                shape_geog=functions.Cast(
                    "shape", models.GeometryField(geography=True, srid=4326)
                )
            )
            .filter(shape_geog__dwithin=(point, 10))
            .exists()
        ):
            continue

        # Check if a report with the same tag exists in a 10 meters radius
        if (
            Report.objects.filter(tags__name="Nouveau bâtiment")
            .annotate(
                point_geog=functions.Cast(
                    "point", models.GeometryField(geography=True, srid=4326)
                )
            )
            .filter(point_geog__dwithin=(point, 10))
            .exists()
        ):
            continue

        Report.create(
            point=point,
            building=None,
            text=text,
            email=None,
            user=team_rnb,
            tags=tags,
            creation_batch_uuid=creation_uuid,
        )
    return creation_uuid
