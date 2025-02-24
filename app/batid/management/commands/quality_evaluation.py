import logging
import unicodedata
from typing import Dict
from typing import List

import requests
from django.contrib.gis.geos import Polygon
from django.core.management.base import BaseCommand

from batid.models import Building

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Evaluates the quality of building addresses by comparing them with OpenStreetMap"
    default_bbox = "-1.696217,48.079933,-1.688106,48.082904"

    def add_arguments(self, parser):
        parser.add_argument(
            "--bbox",
            type=str,
            help='Bounding box in format "min_lon,min_lat,max_lon,max_lat"',
            required=False,
        )

    def handle(self, *args, **options):
        if not options["bbox"]:
            bbox = [float(x) for x in self.default_bbox.split(",")]
        else:
            bbox = [float(x) for x in options["bbox"].split(",")]

        # Get OSM data
        osm_buildings = self._get_osm_buildings(bbox)

        # Get our buildings
        our_buildings = self._get_our_buildings(bbox)

        # Analysis and statistics
        stats = self._compute_statistics(osm_buildings, our_buildings)

        # Display results
        self._display_results(stats)

    def _get_osm_buildings(self, bbox: List[float]) -> List[Dict]:
        """Récupère les bâtiments OSM avec leurs adresses via l'API Overpass"""

        overpass_url = "http://overpass-api.de/api/interpreter"

        query = f"""
        [out:json][timeout:25];
        (
            nwr["addr:street"]["addr:housenumber"]["addr:postcode"]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
        );
        out body;
        >;
        out body qt;
        """

        response = requests.post(overpass_url, data=query)
        if response.status_code != 200:
            logger.error(f"Erreur Overpass API: {response.content}")
            return []

        data = response.json()

        buildings = []
        for element in data.get("elements", []):
            if "tags" in element:
                building = {
                    "id": element["id"],
                    "street_number": element["tags"].get("addr:housenumber"),
                    "street": self.normalize_street(element["tags"].get("addr:street")),
                    "street_rep": self._extract_street_rep(
                        element["tags"].get("addr:housenumber", "")
                    ),
                    "city_zipcode": element["tags"].get("addr:postcode"),
                }
                buildings.append(building)

        return buildings

    def _get_our_buildings(self, bbox: List[float]) -> List[Dict]:
        """Fetches our buildings within the specified bbox"""

        polygon = Polygon.from_bbox(bbox)

        buildings = Building.objects.filter(point__intersects=polygon).prefetch_related(
            "addresses_read_only"
        )

        result = []
        for building in buildings:
            addresses = building.addresses_read_only.all()
            if addresses:
                for address in addresses:
                    result.append(
                        {
                            "id": building.id,
                            "street_number": address.street_number,
                            "street": self.normalize_street(address.street),
                            "street_rep": address.street_rep,
                            "city_zipcode": address.city_zipcode,
                        }
                    )

        return result

    def _compute_statistics(
        self, osm_buildings: List[Dict], our_buildings: List[Dict]
    ) -> Dict:
        """Computes comparison statistics"""

        stats = {
            "total_osm": len(osm_buildings),
            "total_ours": len(our_buildings),
            "matching_addresses": 0,
            "missing_in_our_db": 0,
            "missing_in_osm": 0,
            "different_street_names": 0,
        }

        # Compare addresses
        for osm_building in osm_buildings:
            osm_key = f"{osm_building['street_number']}{osm_building['street_rep']}_{(osm_building['street'])}_{osm_building['city_zipcode']}"

            found_match = False
            for our_building in our_buildings:
                our_key = f"{our_building['street_number']}{our_building['street_rep']}_{(our_building['street'])}_{our_building['city_zipcode']}"

                if osm_key == our_key:
                    stats["matching_addresses"] += 1
                    found_match = True
                    break

            if not found_match:
                stats["missing_in_our_db"] += 1

        # Calculate addresses missing in OSM
        for our_building in our_buildings:
            our_key = f"{our_building['street_number']}{our_building['street_rep']}_{(our_building['street'])}_{our_building['city_zipcode']}"

            found_in_osm = False
            for osm_building in osm_buildings:
                osm_key = f"{osm_building['street_number']}{osm_building['street_rep']}_{(osm_building['street'])}_{osm_building['city_zipcode']}"

                if our_key == osm_key:
                    found_in_osm = True
                    break

            if not found_in_osm:
                stats["missing_in_osm"] += 1

        return stats

    def _display_results(self, stats: Dict):
        """Displays analysis results"""

        self.stdout.write(f"Total OSM buildings: {stats['total_osm']}")
        self.stdout.write(f"Total our buildings: {stats['total_ours']}")
        self.stdout.write(f"Matching addresses: {stats['matching_addresses']}")
        self.stdout.write(
            f"Addresses missing in our database: {stats['missing_in_our_db']}"
        )
        self.stdout.write(f"Addresses missing in OSM: {stats['missing_in_osm']}")
        self.stdout.write(f"Different street names: {stats['different_street_names']}")

        # Calculate percentages
        if stats["total_ours"] > 0:
            coverage = (stats["matching_addresses"] / stats["total_ours"]) * 100
            self.stdout.write(f"\nCoverage rate: {coverage:.2f}%")

    # Create index for faster lookup
    def normalize_street(self, street):
        if not street:
            return ""
        # Remove diacritics
        normalized = "".join(
            c
            for c in unicodedata.normalize("NFKD", street)
            if not unicodedata.combining(c)
        )
        # Convert to lowercase
        return normalized.lower()

    def _extract_street_rep(self, street_number: str) -> str:
        """
        Extracts the street representative from a street number.
        """
        if not street_number:
            return ""

        # Remove spaces and convert to uppercase
        clean_number = street_number.upper().replace(" ", "")

        # Extract non-digit part
        street_rep = "".join(c for c in clean_number if not c.isdigit())

        # Normalize common representations
        if street_rep in ["BIS", "B"]:
            return "B"
        elif street_rep in ["TER", "T"]:
            return "T"
        elif street_rep in ["QUATER", "QUARTER", "Q"]:
            return "Q"

        return street_rep[:1] if street_rep else ""
