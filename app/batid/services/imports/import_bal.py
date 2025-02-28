import csv
import uuid
from collections import defaultdict

import pandas as pd
from batid.services.administrative_areas import dpts_list
from celery import Signature
from django.contrib.gis.geos import MultiPoint
from django.contrib.gis.geos import Point
from django.db import connection

from batid.models import Address
from batid.models import Building
from batid.services.source import Source
from batid.utils.db import dictfetchall


def create_bal_full_import_tasks(dpt_list: list) -> list:

    tasks = []

    bulk_launch_uuid = uuid.uuid4()

    for dpt in dpt_list:

        dpt_tasks = create_bal_dpt_import_tasks(dpt, bulk_launch_uuid)
        tasks.extend(dpt_tasks)

    return tasks


def create_bal_dpt_import_tasks(dpt: str, bulk_launch_id=None) -> list:

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

    # convert_task = Signature(
    #     "batid.tasks.convert_bal",
    #     args=[src_params, bulk_launch_id],
    #     immutable=True,
    # )
    # tasks.append(convert_task)

    # import_task = Signature(
    #     "batid.tasks.import_bal_addresses",
    #     args=[src_params, bulk_launch_id],
    #     immutable=True,
    # )
    # tasks.append(import_task)

    return tasks


def import_addresses(src_params: dict, bulk_launch_uuid=None):

    src = Source("bal")
    src.set_params(src_params)

    return


def convert_bal(src_params, bulk_launch_uuid=None):
    src = Source("bal")
    src.set_params(src_params)

    # FIXME should we create a building_import_history ?

    # Load data
    df = pd.read_csv(src.path, sep=";")
    certified_df = df[df["certification_commune"] == 1]
    certified_df.reset_index(drop=True, inplace=True)

    # Find new adresses
    new_links, old_link_new_ban_id, stats = _create_link_building_address(certified_df)

    # Save to CSV
    if new_links:
        source_filepath = src.find(src.filename)
        output_filepath = source_filepath.replace(".csv", f"_new_links.csv")

        with open(output_filepath, "w", newline="") as csvfile:
            fieldnames = [
                "rnb_id",
                "cle_interop",
                "long",
                "lat",
                "numero",
                "suffixe",
                "voie_nom",
                "commune_nom",
                "commune_insee",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for link in new_links:
                writer.writerow(
                    {
                        "rnb_id": link[0],
                        "cle_interop": link[1],
                        "long": link[2],
                        "lat": link[3],
                        "numero": link[4],
                        "suffixe": link[5],
                        "voie_nom": link[6],
                        "commune_nom": link[7],
                        "commune_insee": link[8],
                    }
                )

        print(f"Exported {len(new_links)} new links to {output_filepath}")

    # Clean up
    src.remove_uncompressed_folder()

    return new_links, old_link_new_ban_id, stats


def insert_bal_addresses(src_params, bulk_launch_uuid=None):
    src = Source("bal")
    src.set_params(src_params)

    # Load data
    source_filepath = src.find(src.filename)
    csv_filepath = source_filepath.replace(".csv", f"_new_links.csv")
    df = pd.read_csv(csv_filepath, sep=";")

    # Process in batches of 100
    batch_size = 100
    total_processed = 0
    total_addresses_added = 0
    total_buildings_updated = 0

    # Process in batches
    for i in range(0, len(df), batch_size):
        batch = df.iloc[i : i + batch_size]

        # Collect all address IDs in the batch
        address_ids = batch["cle_interop"].tolist()
        existing_addresses = set(
            Address.objects.filter(id__in=address_ids).values_list("id", flat=True)
        )

        # Prepare addresses for bulk creation
        addresses_to_create = []
        for _, row in batch.iterrows():
            address_id = row["cle_interop"]
            if address_id not in existing_addresses:
                addresses_to_create.append(
                    Address(
                        id=address_id,
                        source="bal",
                        point=f"POINT ({row['long']} {row['lat']})",
                        street_number=row["numero"],
                        street_rep=row["suffixe"],
                        street=row["voie_nom"],
                        city_name=row["commune_nom"],
                        city_zipcode=None,  # Not available in the CSV
                        city_insee_code=row["commune_insee"],
                    )
                )

        # Bulk create addresses
        addresses_added = 0
        if addresses_to_create:
            try:
                Address.objects.bulk_create(addresses_to_create)
                addresses_added = len(addresses_to_create)
            except Exception as e:
                print(f"Error bulk creating addresses: {str(e)}")

        # Collect all building RNB IDs in the batch
        rnb_ids = batch["rnb_id"].tolist()
        buildings = {b.rnb_id: b for b in Building.objects.filter(rnb_id__in=rnb_ids)}

        # Prepare buildings for bulk update
        buildings_to_update = []
        for _, row in batch.iterrows():
            rnb_id = row["rnb_id"]
            if rnb_id in buildings:
                building = buildings[rnb_id]
                if row["cle_interop"] not in building.addresses_id:
                    building.addresses_id.append(row["cle_interop"])
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
        total_addresses_added += addresses_added

        if i % (batch_size * 10) == 0:
            print(
                f"Processed {total_processed}/{len(df)} rows, added {total_addresses_added} addresses, updated {total_buildings_updated} buildings"
            )

    print(
        f"Completed: processed {total_processed} rows, added {total_addresses_added} addresses, updated {total_buildings_updated} buildings"
    )

    # FIXME: clean up csv files ?


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
                shape__intersects=multi_point, is_active=True
            ).exclude(addresses_id__overlap=excluded_addresses)

            cles_interop_already_linked = set()
            for building in bdgs:
                for point, cle_interop in point_to_cle_interop.items():
                    if building.shape.intersects(point):
                        row = batch[batch["cle_interop"] == cle_interop].iloc[0]
                        already_exists = _address_already_exists(building, row)
                        link = (
                            building.rnb_id,
                            cle_interop,
                            row["long"],
                            row["lat"],
                            row["numero"],
                            row["suffixe"],
                            row["voie_nom"],
                            row["commune_nom"],
                            row["commune_insee"],
                        )
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
                cle_interop_list = [
                    row["cle_interop"] for _, row in other_rows.iterrows()
                ]
                params = {
                    "lng_list": [p[0] for p in points],
                    "lat_list": [p[1] for p in points],
                    "cle_interop_list": cle_interop_list,
                    "buffer_size": 0.00002,  # 0.00002 seems to be a good value to check if the point is close to many plots
                }
                # Print raw sql
                cursor.execute(q, params)
                plots = dictfetchall(cursor, q, params)

                # The bdg matching using plots is tricky. We have to be very conservative.
                # We have many ambiguous situations to filter out:
                # - many obviously independant buildings with different addresses on the same plot. We filter them using building area
                # - address very close to many plots (we filter out the case using a small on address point and removing cases where we intersect multiple plots)
                # - building is not covered enough by a plot
                # we handle those cases along the script

                # Count unique plots and big buildings covered by the plot they intersect
                plots_by_cle_interop = defaultdict(list)
                for plot in plots:
                    plots_by_cle_interop[plot["cle_interop"]].append(plot)

                # Process each point separately
                for _, row in other_rows.iterrows():
                    plots = plots_by_cle_interop[row["cle_interop"]]

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
                    link = (
                        last_bdg["rnb_id"],
                        row["cle_interop"],
                        row["long"],
                        row["lat"],
                        row["numero"],
                        row["suffixe"],
                        row["voie_nom"],
                        row["commune_nom"],
                        row["commune_insee"],
                    )
                    if already_exists:
                        new_ban_id.add(link)
                    else:
                        new_addresses.add(link)

            if batches_handled % 10 == 0:
                print(
                    f"batch : {batches_handled}, found {len(new_addresses)} new links so far and {len(new_ban_id)} existing links but with a new ban id on {batches_handled * batch_size} inspected rows"
                )

    return new_addresses, new_ban_id, stats


def _address_already_exists(bdg, row):
    already_exists = False
    for address in bdg.addresses_read_only.all():
        already_exists = already_exists or (
            address.city_name.lower() == row["commune_nom"].lower()
            and address.street.lower() == row["voie_nom"].lower()
            and int(address.street_number) == row["numero"]
        )
    return already_exists
