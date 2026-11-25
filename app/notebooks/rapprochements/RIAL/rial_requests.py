"""POC: from an RNB building id, list the RIAL (DGFiP) searches to issue.

No RIAL call is made. Rules come from the RIAL functional doc v2026-05:
uppercase inputs, codeVoieTopo on 4 chars, dept on 2 chars (3 for DOM),
codeCommuneInsee on 3 chars (2 for DOM), codeCommuneCadastral always on 3 chars,
numeroPlanParcelle on 4 digits, indiceRepetitionNumeroVoirie on 1 char.
"""

import json
import re
import urllib.request
from dataclasses import dataclass, field

RNB_API = "https://rnb-api.beta.gouv.fr/api/alpha/buildings"
PATH_BY_ADDRESS = "/locaux/adresseTopographique"
PATH_BY_PLOT = "/locaux/parcelleCadastrale"
PATH_DETAIL = "/locaux/{ids}"
DETAIL_MAX_IDS = 200
MAIN_PLOT_MIN_COVER = 0.5

# BAN suffix -> RIAL repetition index (1 char). ponytail: common suffixes only, extend from real rejects.
SUFFIX_TO_INDICE = {"bis": "B", "ter": "T", "quater": "Q", "quinquies": "C"}
TOPO_CODE = re.compile(r"^[A-Z0-9]{4}$")
NO_NUMBER = 99999  # BAN numbering of a lieu-dit without street number


class AddressRejected(ValueError):
    pass


@dataclass
class RialPlan:
    rnb_id: str
    requests: list = field(default_factory=list)  # [{"path": str, "params": dict}]
    discarded: list = field(default_factory=list)  # [{"source": str, "motif": str}]


def split_insee(insee):
    """'93005' -> ('93', '005'); '2A004' -> ('2A', '004'); '97120' -> ('971', '20')."""
    insee = insee.upper()
    if insee.startswith("97"):
        return insee[:3], insee[3:]
    return insee[:2], insee[2:]


def address_params(cle_interop):
    """BAN interop key INSEE_voie_numero[_suffixe] -> RIAL A params. Raises AddressRejected."""
    parts = cle_interop.split("_")
    if len(parts) not in (3, 4):
        raise AddressRejected("clé d'interopérabilité mal formée")
    insee, voie, numero = parts[0].upper(), parts[1].upper(), parts[2]
    if not TOPO_CODE.match(voie):
        raise AddressRejected(
            f"code voie '{parts[1]}' : pseudo-code BAN, pas un code TOPO à 4 caractères"
        )
    if not numero.isdigit() or int(numero) == NO_NUMBER or int(numero) > 9999:
        raise AddressRejected(
            f"numéro '{numero}' : pas un numéro de voirie RIAL (1 à 9999)"
        )
    dept, commune = split_insee(insee)
    params = {
        "codeDepartementInsee": dept,
        "codeCommuneInsee": commune,
        "codeVoieTopo": voie,
        "numeroVoirie": str(int(numero)),
    }
    if len(parts) == 4:
        suffix = parts[3].lower()
        indice = SUFFIX_TO_INDICE.get(suffix) or (
            suffix.upper() if len(suffix) == 1 else None
        )
        if indice is None:
            raise AddressRejected(
                f"suffixe '{parts[3]}' : pas d'indice de répétition RIAL à 1 caractère"
            )
        params["indiceRepetitionNumeroVoirie"] = indice
    return params


def plot_params(plot_id):
    """Etalab plot id (14 chars: INSEE 5 + prefix 3 + section 2 + number 4) -> RIAL B params."""
    plot_id = plot_id.upper()
    if len(plot_id) != 14:
        raise ValueError(f"id parcelle '{plot_id}' : 14 caractères attendus")
    insee, prefix, section, number = (
        plot_id[:5],
        plot_id[5:8],
        plot_id[8:10],
        plot_id[10:],
    )
    dept, _ = split_insee(insee)
    params = {
        "codeDepartementInsee": dept,
        "codeCommuneCadastral": insee[
            2:
        ],  # always 3 chars, DOM included (doc: 97106 -> 106)
        # Etalab pads 1-letter sections with '0' ('0A'); RIAL wants 'A'. Numeric sections (Alsace-Moselle) stay.
        "codeSectionParcelle": (
            section[1] if section[0] == "0" and section[1].isalpha() else section
        ),
        "numeroPlanParcelle": number,
    }
    if prefix != "000":
        params["codeCommuneAbsorbee"] = prefix
    return params


def main_plot(plots):
    """Plot covering at least half of the building, or None."""
    best = max(plots or [], key=lambda p: p["bdg_cover_ratio"], default=None)
    if best and best["bdg_cover_ratio"] >= MAIN_PLOT_MIN_COVER:
        return best
    return None


def plan_requests(building):
    """Pure function: RNB building payload (API format) -> RialPlan."""
    plan = RialPlan(rnb_id=building["rnb_id"])
    for address in building.get("addresses") or []:
        cle = address["id"]
        try:
            plan.requests.append(
                {"path": PATH_BY_ADDRESS, "params": address_params(cle)}
            )
        except AddressRejected as exc:
            plan.discarded.append({"source": f"adresse {cle}", "motif": str(exc)})

    main = main_plot(building.get("plots"))
    if main:
        plan.requests.append({"path": PATH_BY_PLOT, "params": plot_params(main["id"])})
    for plot in building.get("plots") or []:
        if plot is not main:
            plan.discarded.append(
                {
                    "source": f"parcelle {plot['id']}",
                    "motif": f"couvre {plot['bdg_cover_ratio']:.1%} du bâtiment (< {MAIN_PLOT_MIN_COVER:.0%})",
                }
            )
    if not plan.requests:
        plan.discarded.append(
            {"source": "bâtiment", "motif": "aucune recherche RIAL possible"}
        )
    return plan


def fetch_building(rnb_id):
    with urllib.request.urlopen(f"{RNB_API}/{rnb_id}/?withPlots=1", timeout=30) as resp:
        return json.load(resp)


def rial_requests_for(rnb_id):
    """RNB id -> RialPlan (search requests to issue). Detail calls follow: PATH_DETAIL, <= 200 ids each."""
    return plan_requests(fetch_building(rnb_id))


def _self_check():
    assert address_params("94067_7115_00073") == {
        "codeDepartementInsee": "94",
        "codeCommuneInsee": "067",
        "codeVoieTopo": "7115",
        "numeroVoirie": "73",
    }
    assert address_params("2a004_b015_00012_bis") == {
        "codeDepartementInsee": "2A",
        "codeCommuneInsee": "004",
        "codeVoieTopo": "B015",
        "numeroVoirie": "12",
        "indiceRepetitionNumeroVoirie": "B",
    }
    assert address_params("97120_0150_00003_a")["indiceRepetitionNumeroVoirie"] == "A"
    assert address_params("97120_0150_00003")["codeDepartementInsee"] == "971"
    assert address_params("97120_0150_00003")["codeCommuneInsee"] == "20"
    for bad in ("93005_m3p9m8_00001", "93005_3020_99999", "93005_3020_00001_xyz"):
        try:
            address_params(bad)
            raise AssertionError(bad)
        except AddressRejected:
            pass
    assert plot_params("01402000AB0051") == {
        "codeDepartementInsee": "01",
        "codeCommuneCadastral": "402",
        "codeSectionParcelle": "AB",
        "numeroPlanParcelle": "0051",
    }
    assert plot_params("97120000AP0196") == {
        "codeDepartementInsee": "971",
        "codeCommuneCadastral": "120",
        "codeSectionParcelle": "AP",
        "numeroPlanParcelle": "0196",
    }
    assert plot_params("2A0041230A0012") == {
        "codeDepartementInsee": "2A",
        "codeCommuneCadastral": "004",
        "codeCommuneAbsorbee": "123",
        "codeSectionParcelle": "A",
        "numeroPlanParcelle": "0012",
    }
    assert plot_params("57463000010012")["codeSectionParcelle"] == "01"
    assert main_plot([{"id": "x", "bdg_cover_ratio": 0.4}]) is None
    print("self-check OK")


if __name__ == "__main__":
    import sys

    _self_check()
    for rnb_id in sys.argv[1:]:
        plan = rial_requests_for(rnb_id)
        print(f"\n== {rnb_id}")
        for r in plan.requests:
            print("  GET", r["path"], r["params"])
        for d in plan.discarded:
            print("  écarté :", d["source"], "->", d["motif"])
