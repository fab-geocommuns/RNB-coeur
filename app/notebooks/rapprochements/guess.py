import json
import time
from pprint import pprint

import requests


def guess_all(lines, avoid_throttling=False):

    total_len = len(lines)

    if total_len > 100:
        avoid_throttling = True

    print(f"guess all : {total_len} lines")

    results = {}
    for i, line in enumerate(lines):
        print(f"guess line : {i+1}/{total_len}")
        results[line["ext_id"]] = guess(line, avoid_throttling=avoid_throttling)

    return results


# fonction qui appelle le endpoint de notre API dédié aux recherches fuzzy
def guess(params, avoid_throttling=False) -> dict:

    start = time.perf_counter()

    # wait 750 ms between each request (avoir addok throttling)
    if avoid_throttling:
        time.sleep(0.75)

    url = "https://rnb-api.beta.gouv.fr/api/alpha/buildings/guess/"
    q_params = {}

    if params["name"] is not None:
        q_params["name"] = params["name"]
    if params["address"] is not None:
        q_params["address"] = params["address"]
    if params["point"] is not None:
        q_params["point"] = params["point"]

    print("---")
    print(params["ext_id"])
    print(q_params)

    response = requests.get(url, params=q_params)

    if response.status_code == 500 and avoid_throttling:
        print("-- error 500 -- ")
        print("- it might be due to addok throttling -")
        sleep_secs = 10
        print(f"- sleeping for {sleep_secs} seconds -")
        time.sleep(sleep_secs)
        print("- retrying -")
        response = requests.get(url, params=q_params)

    # If the query is still not successful (after eventual throttling avoiding), raise an exception
    if response.status_code == 500:
        raise Exception(f"Error 500 on guessing {q_params}")

    # Results
    params["matches"] = response.json()

    # Performance
    end = time.perf_counter()
    params["time"] = end - start

    return {"q": response.url, "result": params["matches"]}


def analyze(report_path):

    with (open(report_path, "r")) as f:
        data = json.load(f)

    result = {
        "total": len(data),
        "confident": 0,
        "not_confident": 0,
        "not_found": 0,
    }

    for row in data:

        print("----")
        print("ext_id :", row["ext_id"])
        print("name :", row["name"])
        print("address :", row["address"])
        print("point :", row["point"])
        print(
            "first  :",
            row["matches"][0]["rnb_id"],
            row["matches"][0]["score"],
            row["matches"][0].get("sub_scores", None),
        )
        print(
            "second  :",
            row["matches"][1]["rnb_id"],
            row["matches"][1]["score"],
            row["matches"][1].get("sub_scores", None),
        )
        print(
            "third  :",
            row["matches"][2]["rnb_id"],
            row["matches"][2]["score"],
            row["matches"][2].get("sub_scores", None),
        )

        if len(row["matches"]) == 0:
            result["not_found"] += 1
            continue

        if row["matches"][0]["score"] <= 0:
            result["not_found"] += 1
            continue

        if row["matches"][0]["score"] <= 4:
            result["not_confident"] += 1
            continue

        if row["matches"][0]["score"] >= 5:
            result["confident"] += 1
            continue

        result["not_confident"] += 1

    pprint(result)
