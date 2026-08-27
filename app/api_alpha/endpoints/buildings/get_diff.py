import queue
import re
import threading
from collections.abc import Iterator
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

# psycopg2 calls write() once per exported row (~90 bytes), so rows are
# accumulated into chunks of this size before being handed over. Without it, a
# large diff would mean millions of queue operations and as many tiny writes on
# the client socket.
CHUNK_SIZE = 64 * 1024
# Maximum number of chunks waiting to be sent. This bounds the memory used by a
# download in flight (~1 MB) and applies backpressure on the export whenever the
# client reads more slowly than the database produces.
QUEUE_MAX_CHUNKS = 16
# Queue operations wait in slices of this duration rather than blocking forever,
# so that a client who gave up mid-download is noticed.
QUEUE_TIMEOUT_SECONDS = 0.2
# How long the response waits for the export thread to wind down at the end.
THREAD_JOIN_TIMEOUT_SECONDS = 10


def get_datetime_months_ago(months: int) -> datetime:
    return datetime.now(timezone.utc) - relativedelta(days=months * 30)


class _DownloadCancelled(Exception):
    """Raised in the export thread once the client stopped reading the response."""


class _ChunkQueueWriter:
    """
    File-like object bridging the export to the response.

    psycopg2's COPY is push-based: it calls write() on a file object. A
    StreamingHttpResponse is pull-based: it iterates a generator. This object is
    what the export thread writes into, while the response generator reads the
    resulting chunks out of the queue.
    """

    def __init__(
        self, chunks: queue.Queue[bytes | None], cancelled: threading.Event
    ) -> None:
        self.chunks = chunks
        self.cancelled = cancelled
        self.buffer = bytearray()

    def write(self, data: bytes) -> None:
        self.buffer += data
        if len(self.buffer) >= CHUNK_SIZE:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return
        chunk = bytes(self.buffer)
        self.buffer.clear()
        # The queue is bounded, so this blocks while the client is behind. We
        # wait in slices instead of indefinitely, otherwise a client who gave up
        # mid-download would leave this thread stuck here forever.
        while True:
            if self.cancelled.is_set():
                raise _DownloadCancelled()
            try:
                self.chunks.put(chunk, timeout=QUEUE_TIMEOUT_SECONDS)
                return
            except queue.Full:
                continue


def _build_copy_query(
    start_ts: datetime,
    end_ts: datetime,
    city_shape_wkt: str | None,
    with_header: bool,
) -> sql.Composed:
    """Build the COPY statement exporting a single time slice of the diff."""
    spatial_filter = ""
    if city_shape_wkt:
        spatial_filter = (
            " AND ST_Intersects(bb.shape, ST_GeomFromText({city_shape}, 4326))"
        )

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

    if with_header:
        raw_sql = raw_sql + " HEADER"

    format_args = {
        "start": sql.Literal(start_ts.isoformat()),
        "end": sql.Literal(end_ts.isoformat()),
    }
    if city_shape_wkt:
        format_args["city_shape"] = sql.Literal(city_shape_wkt)

    return sql.SQL(raw_sql).format(**format_args)


def _stream_diff(
    since: datetime,
    most_recent_modification: datetime,
    city_shape_wkt: str | None,
    statement_timeout: str,
) -> Iterator[bytes]:
    """
    Yield the diff CSV chunk by chunk, so the client starts receiving data
    while the export is still running.

    The export runs in a thread because psycopg2 pushes the COPY output while
    the response pulls it. That thread gets its own database connection, since
    Django's connections are thread-local, and closing it is up to us:
    close_old_connections only ever runs on the request thread.
    """
    chunks: queue.Queue[bytes | None] = queue.Queue(maxsize=QUEUE_MAX_CHUNKS)
    cancelled = threading.Event()
    failure: list[BaseException] = []

    def export() -> None:
        writer = _ChunkQueueWriter(chunks, cancelled)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SET statement_timeout = %(statement_timeout)s;",
                    {"statement_timeout": statement_timeout},
                )
                start_ts = since
                first_slice = True
                while start_ts < most_recent_modification:
                    end_ts = start_ts + timedelta(days=1)
                    cursor.copy_expert(
                        _build_copy_query(
                            start_ts, end_ts, city_shape_wkt, with_header=first_slice
                        ),
                        writer,
                    )
                    first_slice = False
                    start_ts = end_ts
            writer.flush()
        except _DownloadCancelled:
            # The client stopped reading before the end of the download, for
            # instance because they cancelled it. Nothing went wrong on our
            # side, there is simply nobody left to send the data to.
            pass
        except BaseException as error:
            # Re-raised by the response generator below, so that it is reported
            # with the request context instead of being silently swallowed.
            failure.append(error)
        finally:
            connection.close()
            # Signal the end of the export, waiting in slices for the same
            # reason as the writer does.
            while not cancelled.is_set():
                try:
                    chunks.put(None, timeout=QUEUE_TIMEOUT_SECONDS)
                    break
                except queue.Full:
                    continue

    thread = threading.Thread(target=export, name="diff-export", daemon=True)
    thread.start()
    try:
        while True:
            try:
                chunk = chunks.get(timeout=QUEUE_TIMEOUT_SECONDS)
            except queue.Empty:
                if not thread.is_alive():
                    # The thread is gone without signalling the end of the
                    # export, so nothing more will ever arrive.
                    break
                continue
            if chunk is None:
                break
            yield chunk
        if failure:
            raise failure[0]
    finally:
        # Also reached when the client disconnects, which closes this generator
        # early: telling the thread to stop is what keeps it from leaking.
        cancelled.set()
        thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)


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

        if insee_code:
            filename = f"diff_{insee_code}_{since.isoformat()}_{most_recent_modification.isoformat()}.csv"
        else:
            filename = (
                f"diff_{since.isoformat()}_{most_recent_modification.isoformat()}.csv"
            )

        return StreamingHttpResponse(
            _stream_diff(
                since,
                most_recent_modification,
                city_shape_wkt,
                local_statement_timeout,
            ),
            content_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
