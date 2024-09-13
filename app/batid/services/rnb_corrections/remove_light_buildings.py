from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import pandas as pd
from django.contrib.auth.models import User
from django.db import connection
from django.db import transaction

from batid.models import Building
from batid.models import Fix
from batid.services.administrative_areas import dpts_list
from batid.services.imports.import_bdtopo import bdtopo_src_params
from batid.services.source import Source
from batid.tasks import dl_source


def remove_light_buildings_france(username, fix_id, start_dpt=None, end_dpt=None):
    dpts = dpts_list(start_dpt, end_dpt)

    for dpt in dpts:
        remove_light_buildings(dpt, username, fix_id)


def remove_light_buildings(dpt, username, fix_id):
    src_name = "bdtopo"
    src_params = bdtopo_src_params(dpt, "2024-09-12")
    dl_source(src_name=src_name, src_params=src_params)
    src = Source(src_name)
    bd_topo_path = src.find(src.filename)

    remove_buildings(bd_topo_path, username, fix_id)

    src.remove_uncompressed_folder()


def remove_buildings(bd_topo_path, username, fix_id, max_workers=10):
    df = gpd.read_file(bd_topo_path)
    # select only columns of interest
    df = df[["ID", "IDS_RNB", "LEGER", "geometry"]]
    # filter on light buildings
    df = df[(df["LEGER"] == "Oui") & (df["IDS_RNB"].notnull())]
    # convert to WGS84
    df = df.to_crs("EPSG:4326")

    # split the dataframe into 100 smaller dataframes for multi threading
    if df.shape[0] > 1000:
        dfs = [
            df.iloc[i * df.shape[0] // 100 : (i + 1) * df.shape[0] // 100]
            for i in range(100)
        ]
    else:
        dfs = [df]

    # a match function that will be applied to each row of the dataframe
    def match(row):
        cursor = connection.cursor()
        geometry = row["geometry"]
        rnb_ids = row["IDS_RNB"]

        # if rnb_ids contains "/", split it
        if "/" in rnb_ids:
            rnb_ids_list = rnb_ids.split("/")
        else:
            rnb_ids_list = [rnb_ids]

        matching_rnb_ids = []

        for rnb_id in rnb_ids_list:
            sql = f"""select
            ST_AREA(ST_INTERSECTION(shape,
            ST_GeomFromText('{geometry}', 4326))) / NULLIF(ST_AREA(shape), 0) > 0.9
            from batid_building where rnb_id = '{rnb_id}'"""

            cursor.execute(sql)
            results = cursor.fetchone()

            if results and results[0]:
                matching_rnb_ids.append(rnb_id)

        return matching_rnb_ids

    # the function applied to each small dataframe, that is multi-threaded
    def match_df(df):
        df_copy = df.copy()
        df_copy["match"] = df_copy.apply(match, axis=1)
        return df_copy

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        df_results = executor.map(match_df, dfs)
        df_with_match = pd.concat(df_results)

    # get a list of all the rnb_ids that have been matched
    # and should be removed
    rnb_ids_to_remove = (
        df_with_match[df_with_match["match"].apply(len) > 0]["match"].explode().unique()
    )

    # remove the buildings as a transaction
    with transaction.atomic():
        user = User.objects.get(username=username)
        fix = Fix.objects.get(id=fix_id)

        for rnb_id in rnb_ids_to_remove:
            building = Building.objects.get(rnb_id=rnb_id)
            building.soft_delete(user, {"source": "fix", "id": fix_id})
