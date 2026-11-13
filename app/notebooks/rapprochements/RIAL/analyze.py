"""Measure RNB -> RIAL linkability on the 3 RIAL sandbox communes.

Reads the files written by fetch_communes.py in data/.
"""

import csv
import json
import math
from collections import Counter
from pathlib import Path

from rial_requests import (
    DETAIL_MAX_IDS,
    MAIN_PLOT_MIN_COVER,
    AddressRejected,
    address_params,
    main_plot,
)

DATA_DIR = Path(__file__).parent / "data"
COMMUNES = {"93005": "Aulnay-sous-Bois", "2A004": "Ajaccio", "97120": "Pointe-à-Pitre"}
CALLS_PER_MIN = 50  # RIAL default quota


def pct(*, part, total):
    return f"{100 * part / total:.1f} %" if total else "n/a"


def load_locaux():
    path = DATA_DIR / "communes-locaux-adresses-2024.csv"
    with path.open(encoding="utf-8") as f:
        return {
            r["code_commune"]: int(r["nb_locaux"])
            for r in csv.DictReader(f)
            if r["code_commune"] in COMMUNES
        }


def is_usable(cle):
    try:
        address_params(cle)
        return True
    except AddressRejected:
        return False


def keys(building):
    """Distinct BAN interop keys (INSEE_voie_numero[_suffixe]); drops non-BAN ids."""
    return {
        a["id"]
        for a in building["addresses"] or []
        if len(a["id"].split("_")) in (3, 4)
    }


def analyze(*, insee, nb_locaux):
    lines = (DATA_DIR / f"{insee}.jsonl").read_text(encoding="utf-8").splitlines()
    bdgs = [json.loads(line) for line in lines]
    bdgs = [
        b
        for b in bdgs
        if b["is_active"] and b["status"] in ("constructed", "notUsable")
    ]
    n = len(bdgs)

    addr_bdgs: Counter = Counter()
    for b in bdgs:
        for cle in keys(b):
            addr_bdgs[cle] += 1
    addrs = list(addr_bdgs)
    four = {c for c in addrs if len(c.split("_")[1]) == 4}
    usable = {c for c in addrs if is_usable(c)}
    shared = {c for c in addrs if addr_bdgs[c] > 1}

    plot_bdgs: Counter = Counter()
    for b in bdgs:
        for p in b["plots"] or []:
            if p["bdg_cover_ratio"] >= MAIN_PLOT_MIN_COVER:
                plot_bdgs[p["id"]] += 1

    with_addr = by_a = with_main = by_b = by_a_or_b = no_way = 0
    main_plots = set()
    for b in bdgs:
        cles = keys(b)
        with_addr += bool(cles)
        a_ok = any(c in usable and addr_bdgs[c] == 1 for c in cles)
        by_a += a_ok
        main = main_plot(b["plots"])
        if main:
            with_main += 1
            main_plots.add(main["id"])
        b_ok = bool(main) and plot_bdgs[main["id"]] == 1
        by_b += b_ok
        by_a_or_b += a_ok or b_ok
        no_way += not (cles & four) and not main

    detail_calls = math.ceil(nb_locaux / DETAIL_MAX_IDS)
    searches = len(usable) + len(main_plots)
    hours = (searches + detail_calls) / CALLS_PER_MIN / 60
    return {
        "bâtiments": n,
        "avec au moins une adresse": pct(part=with_addr, total=n),
        "adresses distinctes": len(addrs),
        "adresses au code voie TOPO": pct(part=len(four), total=len(addrs)),
        "adresses partagées par plusieurs bâtiments": pct(
            part=len(shared), total=len(addrs)
        ),
        "seul bâtiment sur une adresse utilisable": pct(part=by_a, total=n),
        "avec une parcelle principale": pct(part=with_main, total=n),
        "seul bâtiment sur sa parcelle principale": pct(part=by_b, total=n),
        "rattachables sans ambiguïté": pct(part=by_a_or_b, total=n),
        "aucune piste": pct(part=no_way, total=n),
        "locaux (MAJIC 2023)": nb_locaux,
        "appels RIAL (recherches + détail)": searches + detail_calls,
        "durée à 50 appels par minute": f"{hours:.1f} h",
    }


if __name__ == "__main__":
    locaux = load_locaux()
    for insee, name in COMMUNES.items():
        print(f"\n== {name} ({insee})")
        for label, value in analyze(insee=insee, nb_locaux=locaux[insee]).items():
            print(f"{label}: {value}")
