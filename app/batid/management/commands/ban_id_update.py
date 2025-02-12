import time
from datetime import datetime
import requests
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.db import transaction
from batid.models import Address, BuildingAddressesReadOnly

class Command(BaseCommand):
    help = "Updates Address IDs using the BAN API"

    def add_arguments(self, parser):
        parser.add_argument(
            '--from-created-at',
            type=str,
            help='Start date of the created_ad field (format YYYY-MM-DD)',
            required=False
        )
        parser.add_argument(
            '--to-created-at',
            type=str,
            help='End date of the created_ad field (format YYYY-MM-DD)',
            required=False
        )
        parser.add_argument(
            '--min-score',
            type=float,
            help='Minimum confidence score from the BAN API',
            required=False,
            default=0.8
        )
        parser.add_argument(
            '--rate-limit',
            type=int,
            help='Number of requests allowed per second',
            required=False,
            default=50
        )

    def handle(self, *args, **options):
        RATE_LIMIT_PER_SECOND = options['rate_limit']
        MIN_TIME_BETWEEN_REQUESTS = 1.0 / RATE_LIMIT_PER_SECOND
        last_request_time = 0

        query = Q()
        if options['start_date']:
            start_date = datetime.strptime(options['start_date'], '%Y-%m-%d')
            query &= Q(created_at__gte=start_date)
        if options['end_date']:
            end_date = datetime.strptime(options['end_date'], '%Y-%m-%d')
            query &= Q(created_at__lte=end_date)

        addresses = Address.objects.filter(query)
        total = addresses.count()
        updated = 0
        errors = 0

        print(f"Starting update of {total} addresses...")

        for address in addresses:
            # Building the query string
            address_parts = []
            if address.street_number:
                address_parts.append(address.street_number)
            if address.street_rep:
                address_parts.append(address.street_rep)
            if address.street:
                address_parts.append(address.street)
            if address.city_name:
                address_parts.append(address.city_name)
            if address.city_zipcode:
                address_parts.append(address.city_zipcode)

            query_string = " ".join(address_parts)

            # Rate limiting
            current_time = time.time()
            time_since_last_request = current_time - last_request_time
            if time_since_last_request < MIN_TIME_BETWEEN_REQUESTS:
                time.sleep(MIN_TIME_BETWEEN_REQUESTS - time_since_last_request)

            # API call
            try:
                response = requests.get(
                    "https://api-adresse.data.gouv.fr/search/",
                    params={"q": query_string},
                    timeout=10
                )
                last_request_time = time.time()

                if response.status_code == 200:
                    data = response.json()
                    if data.get("features") and len(data["features"]) > 0:
                        first_result = data["features"][0]
                        if first_result["properties"].get("score", 0) > options['min_score']:
                            new_id = first_result["properties"].get("id")
                            if new_id and new_id != address.id:
                                old_id = address.id
                                with transaction.atomic():
                                    BuildingAddressesReadOnly.objects.filter(
                                        address_id=old_id
                                    ).update(address_id=new_id)
                                    address.id = new_id
                                    address.save()
                                
                                updated += 1
                                print(f"Address updated: {query_string} -> {new_id}")
                else:
                    errors += 1
                    print(f"API error for {query_string}: {response.status_code}")

            except Exception as e:
                errors += 1
                print(f"Error for {query_string}: {str(e)}")

        print(f"Done! {updated} addresses updated, {errors} errors out of {total} addresses processed")
