import csv
import uuid

from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.db.models.functions import Cast

from batid.models.building import Building
from batid.models.report import Report
from batid.services.bdg_status import BuildingStatus
from batid.services.RNB_team_user import get_RNB_team_user

ARCEP_TAG_NAME = "Nouveau bâtiment"


def dl_and_create_arcep_reports() -> uuid.UUID:
    from batid.services.source import Source

    print("- downloading ARCEP source")
    source = Source("arcep")
    source.download()

    points = []

    print("- reading ARCEP source and creating reports")
    with open(source.find(source.filename), "r") as f:

        reader = csv.DictReader(f)

        idx = 0
        for line in reader:

            idx += 1
            if idx % 100 == 0:
                print(f"- reading line {idx}")

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

    print(f"- creating reports for {len(points)} points")

    creation_uuid = uuid.uuid4()
    team_rnb = get_RNB_team_user()
    tags = [ARCEP_TAG_NAME]

    text = "Un opérateur Internet indique qu'un nouveau bâtiment a été construit ici entre le 01/01/2023 et le 31/12/2025. Faut-il ajouter un nouveau bâtiment au RNB ?"

    for idx, point in enumerate(points):

        if idx % 100 == 0:
            print(f"- processing point {idx}")

        # Check if a real building exists in a 10 meters radius
        q = """
            SELECT id FROM batid_building
            WHERE ST_DWithin(shape::geography, ST_GeomFromText(%(point)s)::geography, 10)
            AND status IN %(status)s
            AND is_active = TRUE
            LIMIT 1
        """
        params = {
            "point": point.wkt,
            "status": tuple(BuildingStatus.REAL_BUILDINGS_STATUS),
        }
        buildings = Building.objects.raw(q, params)

        if any(buildings):
            continue

        # Check if a report with the same tag exists in a 10 meters radius
        q = """
            SELECT r.id FROM batid_report as r
            JOIN taggit_taggeditem AS tagged_item
                ON tagged_item.object_id = r.id
            JOIN django_content_type
                ON tagged_item.content_type_id = django_content_type.id
            JOIN taggit_tag AS tags
                ON tagged_item.tag_id = tags.id
            WHERE django_content_type.app_label = 'batid'
            AND django_content_type.model = 'report'
            AND ST_DWithin(r.point::geography, ST_GeomFromText(%(point)s)::geography, 10)
            AND tags.name = %(tag)s
            LIMIT 1
        """
        params = {"point": point.wkt, "tag": ARCEP_TAG_NAME}
        reports = Report.objects.raw(q, params)
        if any(reports):

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
