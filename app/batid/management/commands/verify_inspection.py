from datetime import datetime
from django.core.management.base import BaseCommand

from batid.services.data_fix.fill_empty_event_origin import building_identicals
from batid.models import Candidate, BuildingWithHistory
from django.db import connection


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("since", type=str, default=None)
        parser.add_argument("--checks", type=str, default="all")

    def handle(self, *args, **options):

        since = options["since"]
        # "Since" is mandatory
        if not since:
            print("Please provide a date.")
            return
        # "Since" must be a valid date
        try:
            since = datetime.strptime(since, "%Y-%m-%d")
        except ValueError:
            print("Please provide a valid date.")
            return

        checks = self._check_to_do(options["checks"])

        if "count_decisions" in checks:
            self._check_count_decisions(since)

        if "count_refusals" in checks:
            self._check_count_refusals(since)

        if "real_updates" in checks:
            self._check_real_updates(since)

    def _check_count_refusals(self, since):

        print(">>> Count refusals per reason")

        q = """
            SELECT inspection_details#>'{reason}' AS reason, count(*) 
            FROM batid_candidate 
            WHERE inspected_at > %(since)s and inspection_details @> '{"decision": "refusal"}'
            GROUP BY inspection_details#>'{reason}';
            """

        with connection.cursor() as cursor:
            cursor.execute(q, {"since": since})
            for row in cursor.fetchall():

                print(f"Reason {row[0]} : {row[1]:_}")

    def _check_count_decisions(self, since):

        print(">>> Count decisions")

        q = """
            SELECT inspection_details#>'{decision}' AS reason, count(*) 
            FROM batid_candidate 
            WHERE inspected_at > %(since)s 
            GROUP BY inspection_details#>'{decision}';
            """

        with connection.cursor() as cursor:
            cursor.execute(q, {"since": since})
            for row in cursor.fetchall():

                print(f"Decision {row[0]} : {row[1]:_}")

    def _check_real_updates(self, since):

        print(">>> Check if updates are real updates")

        """
        We check if each update made from candidate inspection
        has really updated at least one field in the building
        """

        q = """
            SELECT * FROM batid_candidate
            WHERE inspected_at >= %(since)s
            AND  inspection_details @> '{"decision": "update"}'
            limit 100 offset %(offset)s
            """

        params = {
            "since": since,
            "offset": 0,
        }
        batch_size = 1000
        checked_count = 0

        problems = []

        while True:

            print(f"Checked {checked_count} candidates so far")

            candidates = Candidate.objects.raw(q, params)

            if not candidates:
                print("No more candidates to check")
                break

            # We check each updated building
            for candidate in candidates:

                rnb_id = candidate.inspection_details["rnb_id"]

                # todo : this query is ok with a rearely updated database.
                # We may upgrade it to get the right BuildingWithHistory based on a stronger critera
                # than "the last two history rows for this building"
                bdg_history = BuildingWithHistory.objects.filter(
                    rnb_id=rnb_id
                ).order_by("-sys_period")[:2]

                new = bdg_history[0]
                old = bdg_history[1]

                if building_identicals(new, old):
                    problems.append(rnb_id)
                    print(f"Building {rnb_id} has no real update")

                checked_count += 1

            params["offset"] += batch_size

        # Finally, the conclusion
        if problems:
            print(f"{len(problems)} buildings have no real update")
            print(problems)
        else:
            print(f"All ({checked_count}) updates are real updates")

    def _check_to_do(self, requested_checks):

        available_checks = ["real_updates", "count_decisions", "count_refusals"]

        if requested_checks == "all":
            return available_checks

        return list(set(requested_checks.split(",")) & set(available_checks))
