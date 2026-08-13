import os
import re
import traceback
from datetime import datetime, timedelta, timezone

from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import rnb_doc
from batid.models import City
from dateutil.relativedelta import relativedelta  # type: ignore
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.utils.dateparse import parse_datetime
from django.utils.html import escape
from psycopg2 import sql
from rest_framework.views import APIView


def get_datetime_months_ago(months: int) -> datetime:
    return datetime.now(timezone.utc) - relativedelta(days=months * 30)


class DiffView(RNBLoggingMixin, APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Différences depuis une date donnée",
                "description": (
                    "Liste l'ensemble des modifications apportées au RNB depuis une date données. Génère un fichier CSV. Voici les points importants à retenir : <br />"
                    "<ul>"
                    "<li>La colonne action correspond à l'action à mener sur une base local pour la garder synchronisée avec le RNB. Il existe 3 types d'actions : create, update et delete</li>"
                    "<li>Les modifications sont triées par date de modification croissante</li>"
                    "<li>Il est possible qu'un même bâtiment ait plusieurs modifications dans la période considérée. Par exemple, une création (create) suivie d'une mise à jour (update)</li>"
                    "<li>La colonne `event_type` correspond à l'opération réalisée sur le bâtiment (création, désactivation, mise à jour, fusion, scission)</li>"
                    "</ul>"
                    "Par exemple, une fusion de deux bâtiments fera apparaître 3 lignes qui partageront la même action (merge) et le même `event_id`. Les deux bâtiments parents auront l'action `delete` tandis que le bâtiment enfant aura l'action `create`."
                    f"Voici un exemple de requête permettant d'obtenir les modifications du RNB ayant eu lieu depuis une date déterminée : `https://rnb-api.beta.gouv.fr/api/alpha/buildings/diff/?since={datetime.now(timezone.utc) - timedelta(days=1)}`"
                ),
                "operationId": "getDiff",
                "parameters": [
                    {
                        "name": "since",
                        "in": "query",
                        "description": (
                            "Date et heure à partir de laquelle les modifications sont retournées. Le format est ISO 8601. <br />"
                            "La période maximale proposée est de 6 mois.<br/>"
                            "Pour récupérer le RNB dans son intégralité, téléchargez la base de données (l'ensemble de la base est <a href='https://www.data.gouv.fr/fr/datasets/referentiel-national-des-batiments/'>disponible ici</a>). "
                        ),
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "2024-04-02T00:00:00Z",
                    },
                    {
                        "name": "insee_code",
                        "in": "query",
                        "description": (
                            "Code INSEE de la commune pour filtrer les modifications du RNB. "
                            "Seules les modifications de bâtiments dont la géométrie intersecte "
                            "la commune seront retournées. Le code INSEE est composé de 5 caractères."
                        ),
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "75056",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Fichier CSV listant l'ensemble des opérations ayant modifié le RNB depuis la date indiquée.",
                        "content": {
                            "text/csv": {
                                "schema": {"type": "string"},
                                "example": (
                                    "action,rnb_id,status,is_active,sys_period,point,shape,addresses_id,ext_ids,parent_buildings,event_id,event_type,username,user_organization_name,user_organization_id,validated_by"
                                ),
                            }
                        },
                    }
                },
            }
        }
    )
    def get(self, request: HttpRequest) -> HttpResponse | StreamingHttpResponse:
        since_input = request.GET.get("since", "")
        # A '+' in query strings is decoded as a space (HTTP standard).
        # Fix timezone offsets like " 00:00" → "+00:00" at end of string.
        since_input = re.sub(r" (\d{2}:\d{2})$", r"+\1", since_input)
        # parse since to a timestamp
        since = parse_datetime(since_input)
        last_available_modification = get_datetime_months_ago(6)

        if since is None:
            return HttpResponse(
                "The 'since' parameter is missing or incorrect", status=400
            )

        if since.tzinfo is None:
            since = since.astimezone(timezone.utc)

        # nobody should download the whole database
        if since < last_available_modification:
            return HttpResponse(
                f"Maximum diff period is currently 6 months ({last_available_modification}). Please let us know if you need more.",
                status=400,
            )

        # Optional insee_code filter
        insee_code = request.GET.get("insee_code", None)
        city_shape_wkt = None

        if insee_code:
            escaped_insee_code = escape(insee_code)
            try:
                city = City.objects.get(code_insee=insee_code)
            except City.DoesNotExist:
                return HttpResponse(
                    f"Le code INSEE '{escaped_insee_code}' n'a pas été trouvé",
                    status=404,
                )

            if city.shape is None:
                return HttpResponse(
                    f"Erreur interne : la géométrie de la commune '{escaped_insee_code}' est absente",
                    status=500,
                )

            city_shape_wkt = city.shape.wkt

        local_statement_timeout = settings.DIFF_VIEW_POSTGRES_STATEMENT_TIMEOUT
        with connection.cursor() as cursor:
            cursor.execute(
                "SET statement_timeout = %(statement_timeout)s;",
                {"statement_timeout": local_statement_timeout},
            )
            most_recent_modification_query = sql.SQL("""
                select max(lower(sys_period)) from batid_building_with_history
                """)
            cursor.execute(most_recent_modification_query)
            most_recent_modification = cursor.fetchone()[0]

        # The export can take a long time, and we want the client to start
        # receiving data right away instead of waiting for the whole file. So a
        # separate process runs the export and writes into a pipe, while the web
        # server reads from that pipe and sends the result to the client.
        # Could we keep this streaming without a separate process?
        # https://stackoverflow.com/questions/78998534/stream-data-from-postgres-to-http-request-using-django-streaminghttpresponse?noredirect=1#comment139290268_78998534
        #
        # file descriptors r, w for reading and writing
        rfd, wfd = os.pipe()

        # We create that separate process in two steps, and this needs an
        # explanation.
        #
        # The problem: a process that has finished does not disappear by itself.
        # Its parent has to collect its exit code, otherwise the finished process
        # stays in the system's list and keeps using one of the limited number of
        # process slots. The web server (gunicorn) never collects the exit code
        # of processes we create ourselves, so a single process per request would
        # mean one leftover process per download, forever. Once the slots run
        # out, creating any process fails and this endpoint stays broken until
        # the container is restarted.
        #
        # The solution: create a short-lived middle process whose only job is to
        # create the process doing the real work, then stop immediately. We
        # collect the exit code of that middle process straight away, which costs
        # us nothing since it stops at once. The export process is then left with
        # no parent, and the system automatically hands it over to the very first
        # process of the container, which does collect exit codes. So nothing
        # piles up.
        try:
            middle_pid = os.fork()
        except OSError:
            # Close both ends of the pipe, otherwise the file descriptors stay
            # open for the lifetime of the web server and leak on every failure.
            os.close(rfd)
            os.close(wfd)
            raise

        if middle_pid:
            # This is the web server process.
            # It will only read the exported data, we can close w
            os.close(wfd)
            # The middle process stops as soon as it has created the export
            # process, so this wait is very short.
            _, status = os.waitpid(middle_pid, 0)
            if status != 0:
                # The middle process could not create the export process, so
                # nobody will ever write into the pipe.
                os.close(rfd)
                return HttpResponse(
                    "The server is temporarily out of resources, please try again later.",
                    status=503,
                )
            try:
                if insee_code:
                    filename = f"diff_{insee_code}_{since.isoformat()}_{most_recent_modification.isoformat()}.csv"
                else:
                    filename = f"diff_{since.isoformat()}_{most_recent_modification.isoformat()}.csv"
                # data coming from the export process arrives here
                r = os.fdopen(rfd)
            except BaseException:
                # We failed to build the response, so nobody will read the pipe.
                # Closing our end makes the export process stop instead of
                # waiting forever for someone to read what it writes.
                os.close(rfd)
                raise
            return StreamingHttpResponse(
                r,
                content_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        # This is the middle process. It creates the export process and stops
        # right away so the web server process does not have to wait for it.
        try:
            if os.fork():
                os._exit(0)
        except OSError:
            # Tell the web server process we could not create the export process.
            os._exit(1)

        # This is the export process.
        # It will only write data, we can close r
        os.close(rfd)
        w = os.fdopen(wfd, "w")

        # Everything below is wrapped, and this process always ends by calling
        # os._exit(). That is not optional: this process is a copy of the web
        # server and it inherited the network socket the server listens on. If an
        # error escaped from here, the copy would go back into the web server
        # code and start answering requests in parallel with the real server,
        # while never stopping. This happens as soon as a client cancels a
        # download, which is a perfectly normal thing for a client to do.
        try:
            # Abandon the inherited database connection without closing it
            # (the web server process still needs it). Setting connection to None
            # forces Django to create a new connection for this process.
            connection.connection = None

            with connection.cursor() as cursor:
                cursor.execute(
                    "SET statement_timeout = %(statement_timeout)s;",
                    {"statement_timeout": local_statement_timeout},
                )
                start_ts = since
                first_query = True

                while start_ts < most_recent_modification:
                    end_ts = start_ts + timedelta(days=1)

                    spatial_filter = ""
                    if city_shape_wkt:
                        spatial_filter = " AND ST_Intersects(bb.shape, ST_GeomFromText({city_shape}, 4326))"

                    raw_sql = (
                        """
                        COPY (
                            select
                            CASE
                                WHEN event_type = 'delete' THEN 'deactivate'
                                WHEN event_type = 'deactivation' THEN 'deactivate'
                                WHEN event_type = 'update' THEN 'update'
                                WHEN event_type = 'split' and not bb.is_active THEN 'deactivate'
                                WHEN event_type = 'split' and bb.is_active THEN 'create'
                                WHEN event_type = 'merge' and not bb.is_active THEN 'deactivate'
                                WHEN event_type = 'merge' and bb.is_active THEN 'create'
                                WHEN event_type = 'reactivation' THEN 'reactivate'
                                WHEN event_type = 'creation' THEN 'create'
                                WHEN event_type = 'revert_creation' THEN 'deactivate'
                                WHEN event_type = 'revert_update' THEN 'update'
                                WHEN event_type = 'revert_merge' and not bb.is_active THEN 'deactivate'
                                WHEN event_type = 'revert_merge' and bb.is_active THEN 'reactivate'
                                WHEN event_type = 'revert_split' and not bb.is_active THEN 'deactivate'
                                WHEN event_type = 'revert_split' and bb.is_active THEN 'reactivate'
                                ELSE CONCAT('unhandled_event_type_', event_type)
                            END as action,
                            rnb_id,
                            status,
                            bb.is_active::int,
                            sys_period,
                            ST_AsEWKT(point) as point,
                            ST_AsEWKT(shape) as shape,
                            to_json(addresses_id) as addresses_id,
                            COALESCE(ext_ids, '[]'::jsonb) as ext_ids,
                            parent_buildings,
                            event_id,
                            event_type,
                            COALESCE(u.username, 'RNB') as username,
                            org.name as user_organization_name,
                            org.id as user_organization_id,
                            (
                                SELECT COALESCE(json_agg(
                                    json_build_object(
                                        'id', mu.id,
                                        'username', mu.username,
                                        'organization_name', mu_org.name,
                                        'organization_short_name', mu_org.short_name
                                    ) ORDER BY mu.id
                                ), '[]'::json)
                                FROM auth_user mu
                                LEFT JOIN LATERAL (
                                    SELECT org.name, org.short_name
                                    FROM batid_userprofile up
                                    JOIN batid_organization org ON up.organization_id = org.id
                                    WHERE up.user_id = mu.id
                                    LIMIT 1
                                ) AS mu_org ON TRUE
                                WHERE mu.id = ANY(bb.validated_by)
                            ) as validated_by
                            FROM batid_building_with_history bb
                            LEFT JOIN auth_user u on u.id = bb.event_user_id
                            LEFT JOIN batid_userprofile up ON up.user_id = u.id
                            LEFT JOIN batid_organization org ON org.id = up.organization_id
                            where lower(sys_period) > {start}::timestamp with time zone and lower(sys_period) <= {end}::timestamp with time zone"""
                        + spatial_filter  # nosec B608: spatial_filter comes from database (City.shape.wkt), not user input, and is escaped via sql.Literal() below
                        + """
                            order by lower(sys_period), is_active, rnb_id
                        ) TO STDOUT WITH CSV
                        """
                    )

                    if first_query:
                        raw_sql = raw_sql + " HEADER"
                        first_query = False

                    start_literal = start_ts.isoformat()
                    end_literal = end_ts.isoformat()

                    format_args = {
                        "start": sql.Literal(start_literal),
                        "end": sql.Literal(end_literal),
                    }
                    if city_shape_wkt:
                        format_args["city_shape"] = sql.Literal(city_shape_wkt)

                    sql_query = sql.SQL(raw_sql).format(**format_args)
                    # the data coming from the query is streamed to the file descriptor w
                    # and will be received by the parent process as a stream
                    cursor.copy_expert(sql_query, w)
                    start_ts = end_ts
            connection.close()
            # Closing w sends the data still held in memory, so the client gets
            # the end of the file.
            w.close()
        except BrokenPipeError:
            # The client closed the connection before the end of the download,
            # for instance because they cancelled it. Nothing went wrong on our
            # side, there is simply nobody left to send the data to.
            pass
        except BaseException:
            # We report the problem by writing on the error output, which the
            # container collects in its logs. We do not use the usual error
            # reporting tools here: this process is a copy taken while the web
            # server was running several threads at once, and those tools can
            # wait forever for a lock held by a thread that does not exist in the
            # copy. A process stuck forever is exactly what we must avoid.
            os.write(
                2,
                f"Diff export process failed:\n{traceback.format_exc()}".encode(),
            )
        finally:
            # Always stop here, and always with the code 0. The first process of
            # the container reads this code, and gunicorn shuts the whole server
            # down when it reads a 3 or a 4.
            os._exit(0)
