import logging
import uuid

from django.db import connection
from django.db import transaction

from batid.models.building import Building
from batid.models.feve import Feve
from batid.models.others import Department
from batid.models.report import Report
from batid.services.bdg_status import BuildingStatus
from batid.services.RNB_team_user import get_RNB_team_user


def generate_missing_addresses_reports(reports_number, insee_code=None):

    raw_sql = """
select
	bb.rnb_id
from
	batid_building bb
left join batid_report br on
	br.building_id = bb.id
inner join batid_city bc on
	ST_INTERSECTS(bc.shape, bb.shape) and bc.code_insee = %s
where
	st_area(bb.shape::geography) > 100
	and bb.addresses_id = '{}'
	and br.building_id is null
    and bb.is_active
    and (bb.status = ANY(%s))
limit %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            raw_sql, [insee_code, BuildingStatus.REAL_BUILDINGS_STATUS, reports_number]
        )
        rnb_ids = cursor.fetchall()

        with transaction.atomic():
            create_reports(rnb_ids, ["Bâtiment sans adresse"])

        logging.info(
            f"{len(rnb_ids)} signalements ont été créés pour des bâtiments de plus de 100m² sans adresse situé sur la commune ayant pour code insee {insee_code}."
        )


def generate_missing_addresses_reports_dep(reports_number, dep_code):

    raw_sql = """
WITH dep AS (
  SELECT shape AS geom
  FROM batid_department
  WHERE code = %s
),
env AS (
  SELECT ST_Envelope(geom) AS e
  FROM dep
),
params AS (
  SELECT
    (ST_XMax(e) - ST_XMin(e)) / 10.0 AS cell_size
  FROM env
),
cells AS (
  SELECT
    row_number() OVER () AS cell_id,
    g.geom AS cell
  FROM env, params,
  LATERAL ST_SquareGrid(params.cell_size, env.e) AS g
  JOIN dep ON g.geom && dep.geom AND ST_Intersects(g.geom, dep.geom)
)
SELECT
  pick.rnb_id
FROM (
  SELECT * FROM cells
) c
JOIN LATERAL (
  SELECT bb.rnb_id, bb.shape
  FROM batid_building bb
  LEFT JOIN batid_report br ON br.building_id = bb.id
  left join dep on true
  WHERE
    br.building_id IS NULL
    AND bb.is_active
    AND bb.addresses_id = '{}'
    AND bb.status = ANY (%s)
    AND ST_Area(bb.shape) > 0.00000000600
    AND bb.shape && c.cell
    AND ST_Intersects(bb.shape, c.cell)
    AND ST_Intersects(bb.shape, dep.geom)
  LIMIT 3
) pick ON TRUE limit %s;
    """
    # note st_area(bb.shape) > 0.00000000600 is an approximation for 50m², but is much faster

    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout = '0';")
        cursor.execute(
            raw_sql, [dep_code, BuildingStatus.REAL_BUILDINGS_STATUS, reports_number]
        )
        rnb_ids = cursor.fetchall()

        with transaction.atomic():
            creation_batch_uuid = create_reports(
                rnb_ids, ["Bâtiment sans adresse", "Les fèves du RNB"]
            )
            insert_feve(creation_batch_uuid, dep_code)

        logging.info(
            f"{len(rnb_ids)} signalements ont été créés pour des bâtiments de plus de 100m² sans adresse situé dans le département {dep_code}."
        )


def create_reports(rnb_ids, tags):
    creation_uuid = uuid.uuid4()
    team_rnb = get_RNB_team_user()

    for rnb_id in rnb_ids:
        rnb_id = rnb_id[0]
        building = Building.objects.get(rnb_id=rnb_id)

        Report.create(
            point=building.point,  # type: ignore
            building=building,
            text=f"Ce bâtiment d'une surface supérieure à 100m² n'a pas d'adresse associée.",
            email=None,
            user=team_rnb,
            tags=tags,
            creation_batch_uuid=creation_uuid,
        )
    return creation_uuid


def insert_feve(creation_batch_uuid, dep_code):
    reports = Report.objects.filter(creation_batch_uuid=creation_batch_uuid).order_by(
        "?"
    )
    selected_report = reports.first()
    if selected_report:
        department = Department.objects.get(code=dep_code)
        feve = Feve.objects.create(report=selected_report, department=department)
        feve.save()


def generate_the_galettes():
    departments = Department.objects.all()

    for dep in departments:
        logging.info(f"Galette for department {dep.code}.")
        generate_missing_addresses_reports_dep(100, dep.code)
