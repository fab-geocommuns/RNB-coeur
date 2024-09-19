import os
import shutil
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import pandas as pd
from django.contrib.auth.models import User
from django.db import connection
from django.db import transaction

from batid.models import Building
from batid.models import DataFix
from batid.services.administrative_areas import dpts_list
from batid.services.imports.import_bdtopo import bdtopo_src_params
from batid.services.source import Source


def list_light_buildings_france(start_dpt=None, end_dpt=None):
    dpts = dpts_list(start_dpt, end_dpt)
    folder_name = "data_fix_remove_light_buildings"

    # delete the folder if it already exists
    if os.path.exists(folder_name):
        shutil.rmtree(folder_name)

    os.makedirs(folder_name)

    for dpt in dpts:
        list_light_buildings(dpt, folder_name)


def list_light_buildings(dpt, folder_name):
    print(f"Remove light buildings, processing {dpt}")
    print(f"Downloading bdtopo for {dpt}")
    src_name = "bdtopo"
    src_params = bdtopo_src_params(dpt, "2024-06-15")
    src = Source(src_name)
    for param, value in src_params.items():
        src.set_param(param, value)
    src.download()
    src.uncompress()
    src.remove_archive()
    bd_topo_path = src.find(src.filename)

    print(f"Finding light buildings for {dpt}")
    rnb_ids_to_remove = buildings_to_remove(bd_topo_path)
    print("saving results as a file")
    save_results_as_file(rnb_ids_to_remove, dpt, folder_name)
    src.remove_uncompressed_folder()


def save_results_as_file(rnb_ids_to_remove, dpt, folder_name):
    df = pd.DataFrame(rnb_ids_to_remove, columns=["rnb_id"])
    file_path = os.path.join(folder_name, f"{dpt}.csv")
    df.to_csv(file_path, index=False)


def buildings_to_remove(bd_topo_path, max_workers=50):
    print("Reading bdtopo")
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
            sql = f"""
                with contained as (
                select
                    ST_AREA(ST_INTERSECTION(bb.shape,
                    ST_GeomFromText('{geometry}', 4326))) / NULLIF(ST_AREA(bb.shape), 0) > 0.9 as contained
                from
                    batid_building bb
                where
                    bb.rnb_id = '{rnb_id}')
                , neighbors as (
                select
                    count(bb.rnb_id) as count
                from
                    batid_building bb
                left join batid_building bb2 on
                    true
                where
                    bb2.rnb_id = '{rnb_id}'
                    and bb.rnb_id != '{rnb_id}'
                    and ST_DWITHIN(bb.shape, bb2.shape, 0.0)
                ) select contained, count from contained, neighbors;
            """

            cursor.execute(sql)
            results = cursor.fetchone()

            if results and results[0] and results[1] > 0:
                # rnb is contained in bd topo building and has neighbor(s)
                matching_rnb_ids.append(rnb_id)

        return matching_rnb_ids

    # the function applied to each small dataframe, that is multi-threaded
    def match_df(df):
        print("Matching a batch of buildings")
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

    return rnb_ids_to_remove


def remove_light_buildings(folder_name, username, fix_id):
    # read all the csv files in the folder and concatenate them in a single dataframe
    all_files = os.listdir(folder_name)
    dfs = [pd.read_csv(os.path.join(folder_name, f)) for f in all_files]
    df = pd.concat(dfs)

    # remove the buildings as a transaction
    with transaction.atomic():
        user = User.objects.get(username=username)
        DataFix.objects.get(id=fix_id)

        for rnb_id in df["rnb_id"]:
            building = Building.objects.get(rnb_id=rnb_id)
            building.soft_delete(user, {"source": "data_fix", "id": fix_id})

        # if transaction is successful, remove the folder
        transaction.on_commit(lambda: shutil.rmtree(folder_name))
