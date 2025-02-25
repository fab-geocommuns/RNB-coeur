import uuid
import json

from batid.services.imports import building_import_history
from batid.services.source import Source, BufferToCopy
from celery import Signature
from django.contrib.gis.geos import MultiPoint
from collections import defaultdict
from batid.models import Building
from django.db import connection
import pandas as pd
from django.contrib.gis.geos import Point
from batid.utils.db import dictfetchall
from django.db import transaction
import os
import random
from datetime import datetime, timezone
import psycopg2
from batid.models import Candidate

def create_bal_full_import_tasks(dpt_list: list) -> list:

    tasks = []

    bulk_launch_uuid = uuid.uuid4()

    for dpt in dpt_list:

        dpt_tasks = create_bal_dpt_import_tasks(dpt, bulk_launch_uuid)
        tasks.extend(dpt_tasks)

    return tasks


def create_bal_dpt_import_tasks(
    dpt: str, bulk_launch_id=None
) -> list:

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

    convert_task = Signature(
        "batid.tasks.convert_bal",
        args=[src_params, bulk_launch_id],
        immutable=True,
    )
    tasks.append(convert_task)

    return tasks

def create_candidate_from_bal(src_params, bulk_launch_uuid=None):
    src = Source("bal")
    src.set_params(src_params)

    # Create building import
    building_import = building_import_history.insert_building_import(
        "bal", bulk_launch_uuid, src_params["dpt"]
    )

    # Load data
    df = pd.read_csv(src.find(src.filename))
    certified_df = df[df['certification_commune'] == 1]    
    certified_df.reset_index(drop=True, inplace=True)

    # Fond new adresses
    new_links, old_link_new_ban_id, stats = _create_link_building_address(certified_df)

    # Create Candidates
    candidates = []
    for rnb_id, cle_interop, commune_nom, voie_nom, numero in new_links:
        candidate = {
            "source": "bal",
            "source_id": cle_interop,
            "address_keys": f"{{{cle_interop}}}",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "random": random.randint(0, 1000000000),
            "created_by": json.dumps({"source": "import", "id": building_import.id}),
            "source_version": src_params.get("date")
        }
        candidates.append(candidate)

    # Save to DB
    if candidates:
        buffer = BufferToCopy()
        buffer.write_data(candidates)

        cols = candidates[0].keys()

        with open(buffer.path, "r") as f:
            with transaction.atomic():
                try:
                    with connection.cursor() as cursor:
                        cursor.copy_from(
                            f, Candidate._meta.db_table, sep=";", columns=cols
                        )

                    building_import_history.increment_created_candidates(
                        building_import, len(candidates)
                    )

                except (Exception, psycopg2.DatabaseError) as error:
                    raise error

        # Clean up
        os.remove(buffer.path)
        src.remove_uncompressed_folder()

    return new_links, old_link_new_ban_id, stats


def _create_link_building_address(certified_df):
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

    new_addresses = set()
    new_ban_id = set()

    batch_size = 200
    batches_handled = 0

    batches = certified_df.reset_index(drop=True)
    batches = batches.groupby(batches.index // batch_size)

    stats = {
        "ambigous_multi_plots": 0,
        "no_covered_building": 0,
        "multiple_covered_building": 0,
        "address_already_exists": 0,
    }

    with connection.cursor() as cursor:
        for i, batch in batches:
            batches_handled += 1

            points = [(row["long"], row["lat"]) for _, row in batch.iterrows()]
            point_to_cle_interop = {
                Point(row["long"], row["lat"], srid=4326): row["cle_interop"]
                for _, row in batch.iterrows()
            }

            # ##################
            # First we test with the most precise method
            excluded_addresses = [row["cle_interop"] for _, row in batch.iterrows()]
            points_list = [Point(lng, lat, srid=4326) for lng, lat in points]
            multi_point = MultiPoint(points_list, srid=4326)

            bdgs = Building.objects.filter(
                shape__intersects=multi_point,
                is_active=True
            ).exclude(addresses_id__overlap=excluded_addresses)

            cles_interop_already_linked = set()
            for building in bdgs:
                for point, cle_interop in point_to_cle_interop.items():
                    if building.shape.intersects(point):
                        row = batch[batch["cle_interop"] == cle_interop].iloc[0]
                        already_exists = _address_already_exists(building, row)
                        link = (building.rnb_id, cle_interop, row["commune_nom"], row["voie_nom"], row["numero"])
                        cles_interop_already_linked.add(cle_interop)
                        if already_exists:
                            new_ban_id.add(link)
                        else:
                            new_addresses.add(link)

            # ##################
            # If we found no precise match, we continue with a less precise method using plots
            other_rows = batch[~batch["cle_interop"].isin(cles_interop_already_linked)]
            if len(other_rows) > 0:
                points = [(row["long"], row["lat"]) for _, row in other_rows.iterrows()]
                cle_interop_list = [row["cle_interop"] for _, row in other_rows.iterrows()]
                params = {
                    "lng_list": [p[0] for p in points],
                    "lat_list": [p[1] for p in points],
                    "cle_interop_list": cle_interop_list,
                    "buffer_size": 0.00002 # 0.00002 seems to be a good value to check if the point is close to many plots
                }
                # Print raw sql
                cursor.execute(q, params)
                plots = dictfetchall(cursor, q, params)

                # pprint(plots)

                # The bdg matching using plots is tricky. We have to be very conservative.
                # We have many ambiguous situations to filter out:
                # - many obviously independant buildings with different addresses on the same plot. We filter them using building area
                # - address very close to many plots (we filter out the case using a small on address point and removing cases where we intersect multiple plots)
                # - building is not covered enough by a plot
                # we handle those cases along the script

                # Count unique plots and big buildings covered by the plot they intersect
                plots_by_cle_interop = defaultdict(list)
                for plot in plots:
                    plots_by_cle_interop[plot['cle_interop']].append(plot)

                # Process each point separately
                for _, row in other_rows.iterrows():
                    plots = plots_by_cle_interop[row['cle_interop']]

                    # Get unique plots for this point
                    plots_ids = {plot["plot_id"] for plot in plots}
                    covered_enough_big_bdgs = []

                    for plot in plots:
                        if plot["rnb_id"] and plot["bdg_cover_ratio"] > 0.75 and plot["bdg_area"] >= 35:
                            covered_enough_big_bdgs.append({
                                'rnb_id': plot['rnb_id'],
                                'addresses': plot['bdg_addresses']
                            })

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
                    if row['cle_interop'] in last_bdg['addresses']:
                        stats["address_already_exists"] += 1
                        continue

                    bdg = Building.objects.filter(rnb_id=last_bdg['rnb_id']).prefetch_related("addresses_read_only").get()
                    already_exists = _address_already_exists(bdg, row)
                    link = (last_bdg["rnb_id"], row['cle_interop'], row["commune_nom"], row["voie_nom"], row["numero"])
                    if already_exists:
                        new_ban_id.add(link)
                    else:
                        new_addresses.add(link)

            if batches_handled % 10 == 0:
                print(f"batch : {batches_handled}, found {len(new_addresses)} new links so far and {len(new_ban_id)} existing links but with a new ban id on {batches_handled * batch_size} inspected rows")

    return new_addresses, new_ban_id, stats

def _address_already_exists(bdg, row):
    already_exists = False
    for address in bdg.addresses_read_only.all():
        already_exists = already_exists or (address.city_name.lower() == row['commune_nom'].lower() and address.street.lower() == row['voie_nom'].lower() and int(address.street_number) == row['numero'])
    return already_exists