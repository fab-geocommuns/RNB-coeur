import csv
import time
import uuid

from celery import Signature
from django.contrib.gis.geos import MultiPoint
from django.contrib.gis.geos import Point
from django.db import connection

from batid.models import Address
from batid.models import Building
from batid.services.imports import building_import_history
from batid.services.source import Source
from batid.utils.db import dictfetchall


def create_bal_full_import_tasks(dpt_list: list) -> list:

    tasks = []

    bulk_launch_uuid = uuid.uuid4()

    for dpt in dpt_list:

        dpt_tasks = _create_bal_dpt_import_tasks(dpt, bulk_launch_uuid)
        tasks.extend(dpt_tasks)

    return tasks


def _create_bal_dpt_import_tasks(dpt: str, bulk_launch_id=None) -> list:

    tasks = []
    src_params = {
        "dpt": dpt.zfill(2),
    }

    dl_task = Signature(
        "batid.tasks.dl_source",
        args=["bal", src_params],
        immutable=True,
    )
    tasks.append(dl_task)

    task = Signature(
        "batid.tasks.import_bal", args=[src_params, bulk_launch_id], immutable=True
    )
    tasks.append(task)

    convert_task = Signature(
        "batid.tasks.link_building_addresses_using_bal",
        args=[src_params, bulk_launch_id],
        immutable=True,
    )
    tasks.append(convert_task)

    return tasks


def import_addresses(src_params: dict, bulk_launch_uuid=None):

    src = Source("bal")
    src.set_params(src_params)

    building_import_history.insert_building_import(
        "bal", bulk_launch_uuid, src_params["dpt"]
    )

    with open(src.find(src.filename), "r") as f:
        reader = csv.DictReader(f, delimiter=";")

        addresses_batch = []
        batch_size = 100000
        adresses_count = 0
        start_time = time.perf_counter()

        for row in reader:

            if row["certification_commune"] != "1":
                continue

            adresses_count += 1

            addresses_batch.append(
                Address(
                    id=row["cle_interop"],
                    source="BAL",
                    point=Point(float(row["long"]), float(row["lat"]), srid=4326),
                    street_number=row["numero"],
                    street_rep=row["suffixe"],
                    street=row["voie_nom"],
                    city_name=row["commune_nom"],
                    city_zipcode=None,  # FIXME: find the related zipcode from INSEE code (maybe using: https://www.data.gouv.fr/en/datasets/base-officielle-des-codes-postaux/)
                    city_insee_code=row["commune_insee"],
                )
            )

            if len(addresses_batch) >= batch_size:
                Address.objects.bulk_create(addresses_batch, ignore_conflicts=True)
                addresses_batch = []

        Address.objects.bulk_create(addresses_batch, ignore_conflicts=True)
        end_time = time.perf_counter()
        print(f"Duration: {(end_time - start_time):.2f}s")

    return f"Imported {adresses_count} BAN addresses"


def link_building_with_addresses(src_params, bulk_launch_uuid=None):
    src = Source("bal")
    src.set_params(src_params)

    # Load data
    certified_rows = []
    with open(src.find(src.filename), "r") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            if row["certification_commune"] == "1":
                certified_rows.append(row)

    # Find new adresses
    start_time = time.perf_counter()
    new_links, _, stats = _find_link_building_with_address(certified_rows)
    stats["find_link_total_time"] = time.perf_counter() - start_time

    # Create new links
    if new_links:
        start_time = time.perf_counter()
        _save_new_links(new_links)
        stats["save_new_links_total_time"] = time.perf_counter() - start_time

    # Clean up
    src.remove_uncompressed_folder()

    return stats


def _find_link_building_with_address(certified_rows: list[dict[str, str]]):
    q = """
        WITH points AS (
            SELECT unnest(%(lng_list)s) AS lng,
                unnest(%(lat_list)s) AS lat,
                unnest(%(cle_interop_list)s) AS cle_interop
        )
        SELECT
            p.id AS plot_id,
            b.rnb_id AS rnb_id,
            st_area(st_intersection(b.shape, p.shape)) / st_area(b.shape) AS bdg_cover_ratio,
            st_area(b.shape::geography) AS bdg_area,
            b.addresses_id AS bdg_addresses,
            pt.lng,
            pt.lat,
            pt.cle_interop
        FROM points pt
        JOIN LATERAL (
            SELECT * FROM batid_plot
            WHERE shape && st_expand(st_setsrid(st_makepoint(pt.lng, pt.lat), 4326), %(buffer_size)s)
            AND st_intersects(shape, st_buffer(st_setsrid(st_makepoint(pt.lng, pt.lat), 4326), %(buffer_size)s))
        ) p ON TRUE
        LEFT JOIN batid_building AS b ON b.shape && p.shape
            AND st_intersects(p.shape, b.shape)
        WHERE ST_GeometryType(b.shape) != 'ST_Point';
        """

    new_addresses: list[dict[str, str]] = list()
    new_ban_id: list[dict[str, str]] = list()

    batch_size = 200
    batches_handled = 0
    total_rows = len(certified_rows)

    # Create batches of rows
    batches = [
        certified_rows[i : i + batch_size] for i in range(0, total_rows, batch_size)
    ]

    stats = {
        "ambigous_multi_plots": 0,
        "no_covered_building": 0,
        "multiple_covered_building": 0,
        "address_already_exists": 0,
        "total_bal_rows_treated": 0,
        "existing_link_with_new_bal_id": 0,
        "find_link_mean_time_per_batch": 0,
        "find_link_mean_time_per_sql_query": 0,
    }

    time_per_batch = []
    time_per_sql_query = []
    with connection.cursor() as cursor:
        for batch in batches:
            start_time_per_batch = time.perf_counter()
            batches_handled += 1

            # Create points from the batch
            points = [(float(row["long"]), float(row["lat"])) for row in batch]
            point_to_cle_interop = {
                Point(float(row["long"]), float(row["lat"]), srid=4326): row[
                    "cle_interop"
                ]
                for row in batch
            }

            # 1) we test with the most precise method (BAL point in shape)
            excluded_addresses = [row["cle_interop"] for row in batch]
            points_list = [Point(lng, lat, srid=4326) for lng, lat in points]
            multi_point = MultiPoint(points_list, srid=4326)

            bdgs = Building.objects.filter(
                shape__intersects=multi_point, is_active=True
            ).exclude(addresses_id__overlap=excluded_addresses)

            cles_interop_already_linked = set()
            for building in bdgs:
                for point, cle_interop in point_to_cle_interop.items():
                    if building.shape.intersects(point):
                        # Find the row with matching cle_interop
                        row = next(
                            (r for r in batch if r["cle_interop"] == cle_interop), None
                        )
                        if row:
                            already_exists = _address_already_exists(building, row)
                            link = {
                                "rnb_id": building.rnb_id,
                                "cle_interop": cle_interop,
                                "long": row["long"],
                                "lat": row["lat"],
                                "numero": row["numero"],
                                "suffixe": row["suffixe"],
                                "voie_nom": row["voie_nom"],
                                "commune_nom": row["commune_nom"],
                                "commune_insee": row["commune_insee"],
                            }
                            cles_interop_already_linked.add(cle_interop)
                            if already_exists:
                                new_ban_id.append(link)
                            else:
                                new_addresses.append(link)

            # 2) If we found no precise match, we continue with a less precise method using plots
            other_rows = [
                row
                for row in batch
                if row["cle_interop"] not in cles_interop_already_linked
            ]
            if len(other_rows) > 0:
                points = [(float(row["long"]), float(row["lat"])) for row in other_rows]
                cle_interop_list = [row["cle_interop"] for row in other_rows]
                params = {
                    "lng_list": [p[0] for p in points],
                    "lat_list": [p[1] for p in points],
                    "cle_interop_list": cle_interop_list,
                    "buffer_size": 0.00002,  # 0.00002 seems to be a good value to check if the point is close to many plots
                }

                start_time_per_sql_query = time.perf_counter()
                plots = dictfetchall(cursor, q, params)
                time_per_sql_query.append(time.perf_counter() - start_time_per_sql_query)

                # The bdg matching using plots is tricky. We have to be very conservative.
                # We have many ambiguous situations to filter out:
                # - many obviously independant buildings with different addresses on the same plot. We filter them using building area
                # - address very close to many plots (we filter out the case using a small on address point and removing cases where we intersect multiple plots)
                # - building is not covered enough by a plot
                # we handle those cases along the script

                for row in other_rows:
                    plots = [
                        plot
                        for plot in plots
                        if plot["cle_interop"] == row["cle_interop"]
                    ]

                    # Get unique plots for this point
                    plots_ids = {plot["plot_id"] for plot in plots}
                    covered_enough_big_bdgs = []

                    for plot in plots:
                        if (
                            plot["rnb_id"]
                            and plot["bdg_cover_ratio"] > 0.75
                            and plot["bdg_area"] >= 35
                        ):
                            covered_enough_big_bdgs.append(
                                {
                                    "rnb_id": plot["rnb_id"],
                                    "addresses": plot["bdg_addresses"],
                                }
                            )

                    # If we have many plots, it is too ambiguous, we skip
                    if len(plots_ids) > 1:
                        stats["ambigous_multi_plots"] += 1
                        continue

                    # If we have none, it is too ambiguous, we skip
                    if len(covered_enough_big_bdgs) == 0:
                        stats["no_covered_building"] += 1
                        continue

                    # If we have many big buildings, it is too ambiguous, we skip
                    if len(covered_enough_big_bdgs) > 1:
                        stats["multiple_covered_building"] += 1
                        continue

                    # We now have one building in one plot
                    last_bdg = covered_enough_big_bdgs[0]

                    # We check the cle_interop is not already linked to the bdg
                    if row["cle_interop"] in last_bdg["addresses"]:
                        stats["address_already_exists"] += 1
                        continue

                    bdg = (
                        Building.objects.filter(rnb_id=last_bdg["rnb_id"])
                        .prefetch_related("addresses_read_only")
                        .get()
                    )
                    already_exists = _address_already_exists(bdg, row)
                    link = {
                        "rnb_id": last_bdg["rnb_id"],
                        "cle_interop": row["cle_interop"],
                        "long": row["long"],
                        "lat": row["lat"],
                        "numero": row["numero"],
                        "suffixe": row["suffixe"],
                        "voie_nom": row["voie_nom"],
                        "commune_nom": row["commune_nom"],
                        "commune_insee": row["commune_insee"],
                    }

                    if already_exists:
                        new_ban_id.append(link)
                    else:
                        new_addresses.append(link)

            time_per_batch.append(time.perf_counter() - start_time_per_batch)

            if batches_handled % 10 == 0:
                stats["total_bal_rows_treated"] += len(batch)
                stats["existing_link_with_new_bal_id"] += len(new_ban_id)
                print(
                    f"batch : {batches_handled}, found {len(new_addresses)} new links so far and {len(new_ban_id)} existing links but with a new ban id on {batches_handled * batch_size} inspected rows"
                )

    stats["find_link_mean_time_per_batch"] = sum(time_per_batch) / len(time_per_batch)
    stats["find_link_mean_time_per_sql_query"] = sum(time_per_sql_query) / len(
        time_per_sql_query
    )
    return new_addresses, new_ban_id, stats


def _save_new_links(new_links):
    # Process in batches of 100
    batch_size = 100
    total_processed = 0
    total_buildings_updated = 0

    # Process in batches
    for i in range(0, len(new_links), batch_size):
        batch = new_links[i : i + batch_size]

        # Collect all building RNB IDs in the batch
        rnb_ids = [link["rnb_id"] for link in batch]
        buildings = {b.rnb_id: b for b in Building.objects.filter(rnb_id__in=rnb_ids)}

        # Prepare buildings for bulk update
        buildings_to_update = []
        for link in batch:
            rnb_id = link["rnb_id"]
            if rnb_id in buildings:
                building = buildings[rnb_id]
                if link["cle_interop"] not in building.addresses_id:
                    building.addresses_id.append(link["cle_interop"])
                    buildings_to_update.append(building)
            else:
                print(f"Building with rnb_id {rnb_id} not found")

        # Bulk update buildings
        if buildings_to_update:
            try:
                Building.objects.bulk_update(buildings_to_update, ["addresses_id"])
                total_buildings_updated += len(buildings_to_update)
            except Exception as e:
                print(f"Error bulk updating buildings: {str(e)}")

        total_processed += len(batch)

        if i % (batch_size * 10) == 0:
            print(
                f"Processed {total_processed}/{len(new_links)} rows, updated {total_buildings_updated} buildings"
            )

    print(
        f"Completed: processed {total_processed} rows, updated {total_buildings_updated} buildings"
    )

    # FIXME: clean up csv files ?


def _address_already_exists(bdg: Building, row: dict[str, str]):
    already_exists = False
    for address in bdg.addresses_read_only.all():
        already_exists = already_exists or (
            address.city_name.lower() == row["commune_nom"].lower()
            and address.street.lower() == row["voie_nom"].lower()
            and int(address.street_number) == int(row["numero"])
        )
    return already_exists
