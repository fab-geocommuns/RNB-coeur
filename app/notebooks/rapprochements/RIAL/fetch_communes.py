"""Download the inputs of analyze.py for the 3 RIAL sandbox communes.

Outputs, in data/:
- <insee>.jsonl: active RNB buildings (API default = constructed + notUsable),
  one per line (rnb_id, status, addresses, plots)
- communes-locaux-adresses-2024.csv: number of fiscal premises per commune
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

API = "https://rnb-api.beta.gouv.fr/api/alpha/buildings/"
LOCAUX_CSV = (
    "https://static.data.gouv.fr/resources/nombre-de-locaux-adressables-par-communes/"
    "20240911-121358/communes-locaux-adresses-2024.csv"
)
COMMUNES = {"93005": "Aulnay-sous-Bois", "2A004": "Ajaccio", "97120": "Pointe-à-Pitre"}
DATA_DIR = Path(__file__).parent / "data"
DELAY_S = 0.25  # stay under ~4 requests per second on the public API


def get_json(url):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.load(resp)
        except OSError as exc:  # network error, 5xx or 429: wait and retry
            print(f"  retry {attempt + 1} on {url}: {exc}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"failed: {url}")


def fetch_commune(insee):
    url = f"{API}?insee_code={insee}&withPlots=1&limit=100"
    out = DATA_DIR / f"{insee}.jsonl"
    count = 0
    with out.open("w", encoding="utf-8") as f:
        while url:
            page = get_json(url)
            for b in page["results"]:
                keep = {
                    k: b[k]
                    for k in ("rnb_id", "status", "is_active", "addresses", "plots")
                }
                f.write(json.dumps(keep, ensure_ascii=False) + "\n")
                count += 1
            url = page["next"]
            time.sleep(DELAY_S)
    print(f"{insee} {COMMUNES[insee]}: {count} buildings -> {out}")


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    urllib.request.urlretrieve(
        LOCAUX_CSV, DATA_DIR / "communes-locaux-adresses-2024.csv"
    )
    for insee in COMMUNES:
        fetch_commune(insee)
