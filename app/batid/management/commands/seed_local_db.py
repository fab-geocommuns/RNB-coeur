import os
import readline  # noqa: F401 (enables line editing and history in input())
import sys
from getpass import getpass

import psycopg2
from batid.services.local_seed import (
    MAX_RADIUS_KM,
    SeedConfigError,
    build_zones,
    check_target_is_local,
    count_rows,
    parse_points,
    seed,
    target_is_empty,
)
from django.core.management.base import BaseCommand, CommandError

DEFAULT_RADIUS_KM = 1.0


class Command(BaseCommand):
    help = (
        "Seed the local database with the buildings and addresses located around "
        "GPS points, extracted from a remote RNB database (eg. the sandbox). "
        "Each parameter is read from the command line, then from the SEED_* "
        "environment variables (.env.seed.dev), and is asked interactively otherwise."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--point",
            action="append",
            # several tokens, so that "--point 48.85, 2.29" (split by the shell
            # after the comma) is accepted too
            nargs="+",
            help='Center of a zone, as "lat,lon". Can be repeated. Env: SEED_POINTS="lat,lon;lat,lon"',
        )
        parser.add_argument(
            "--radius-km",
            type=float,
            help=f"Radius around each point, in km (max {MAX_RADIUS_KM}). Env: SEED_RADIUS_KM",
        )
        parser.add_argument(
            "--source-dsn",
            help="Connection string of the source database. Env: SEED_SOURCE_DSN",
        )
        parser.add_argument(
            "--truncate",
            action="store_true",
            help="Empty the local building, address, city and department tables first",
        )
        parser.add_argument(
            "--yes", action="store_true", help="Do not ask for confirmation"
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Never prompt: fail if a parameter is missing",
        )

    def handle(self, *args, **options):
        self.interactive = not options["no_input"] and sys.stdin.isatty()

        try:
            check_target_is_local()
        except SeedConfigError as e:
            raise CommandError(str(e))

        zones = self._resolve_zones(options)
        dsn = self._resolve_dsn(options)

        self.stdout.write("Connexion à la base source…")
        try:
            source_conn = psycopg2.connect(dsn)
        except psycopg2.OperationalError as e:
            raise CommandError(f"Connexion à la base source impossible : {e}")
        # the source is only read, never written
        source_conn.set_session(readonly=True)

        try:
            self._run(source_conn, zones, options)
        finally:
            source_conn.close()

    def _run(self, source_conn, zones, options):
        self.stdout.write("Zones :")
        for z in zones:
            self.stdout.write(f"  - ({z.lat}, {z.lon}), rayon {z.radius_m / 1000} km")

        self.stdout.write("Estimation du volume sur la source…")
        counts = count_rows(source_conn, zones)
        for table, count in counts.items():
            self.stdout.write(f"  {table} : {count} lignes")

        truncate = options["truncate"]
        if not truncate and not target_is_empty():
            if not self._confirm(
                "La base locale contient déjà des bâtiments, adresses ou communes. "
                "Les vider (ainsi que les signalements et autres tables liées) ?"
            ):
                raise CommandError(
                    "Base locale non vide : relancer avec --truncate pour la vider"
                )
            truncate = True

        if not options["yes"] and not self._confirm("Lancer l'import ?"):
            self.stdout.write("Import annulé")
            return

        self.stdout.write("Import…")
        seed(source_conn, zones, truncate=truncate, log=self.stdout.write)
        self.stdout.write(self.style.SUCCESS("Base locale prête"))
        self.stdout.write(
            "Pour créer un compte admin : docker exec -it web python manage.py createsuperuser"
        )

    # -- parameter resolution: command line > environment > prompt ----------

    def _resolve_zones(self, options):
        raw_points = (
            ";".join(" ".join(tokens) for tokens in options["point"])
            if options["point"]
            else os.environ.get("SEED_POINTS")
        )
        raw_radius = options["radius_km"] or os.environ.get("SEED_RADIUS_KM")

        while True:
            if not raw_points:
                raw_points = self._ask(
                    'Point(s) au format "lat,lon", séparés par ";" (ex: 48.8584,2.2945) : '
                )
            if not raw_radius:
                raw_radius = (
                    self._ask(f"Rayon en km [{DEFAULT_RADIUS_KM}] : ")
                    or DEFAULT_RADIUS_KM
                )
            try:
                return build_zones(parse_points(raw_points), float(raw_radius))
            except (SeedConfigError, ValueError) as e:
                if not self.interactive:
                    raise CommandError(str(e))
                self.stderr.write(str(e))
                # ask again for both values
                raw_points = raw_radius = None

    def _resolve_dsn(self, options):
        dsn = options["source_dsn"] or os.environ.get("SEED_SOURCE_DSN")
        if dsn:
            return dsn
        if not self.interactive:
            raise CommandError("Paramètre manquant : --source-dsn ou SEED_SOURCE_DSN")
        # the DSN usually contains a password: do not echo it
        return getpass(
            "DSN de la base source (ex: postgresql://user:password@host:5432/db) : "
        )

    def _ask(self, prompt):
        if not self.interactive:
            raise CommandError(f"Paramètre manquant ({prompt.strip(' :')})")
        return input(prompt).strip()

    def _confirm(self, question):
        if not self.interactive:
            return False
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes", "o", "oui")
