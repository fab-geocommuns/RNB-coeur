import queue
import re
import threading
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import rnb_doc
from batid.models import City
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.utils.dateparse import parse_datetime
from django.utils.html import escape
from psycopg import sql
from rest_framework.views import APIView

# The COPY yields one message per exported row (~90 bytes), so rows are
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


# Oldest point in time a diff can start from, in sliding days.
MAX_DIFF_DAYS = 180
# Date used as `since` in the doc examples: recent enough to be accepted.
SINCE_EXAMPLE = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
    "%Y-%m-%dT00:00:00Z"
)


class _DownloadCancelled(Exception):
    """Raised in the export thread once the client stopped reading the response."""


class _ChunkQueueWriter:
    """
    File-like object bridging the export to the response.

    The export thread writes the COPY rows into this object, while the
    StreamingHttpResponse, which is pull-based, iterates a generator reading the
    resulting chunks out of the queue.
    """

    def __init__(
        self, chunks: queue.Queue[bytes | None], cancelled: threading.Event
    ) -> None:
        self.chunks = chunks
        self.cancelled = cancelled
        self.buffer = bytearray()

    def write(self, data: bytes | memoryview) -> None:
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
            " AND ST_Intersects(bb.point, ST_GeomFromText({city_shape}, 4326))"
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
            -- The public contract exposes BAN "clés d'interopérabilité", while the
            -- link is read from addresses_internal_id (batid_address.internal_id
            -- values): translate them back, keeping the array order.
            -- to_json(array_agg()) rather than json_agg() to keep the exact former
            -- formatting (json_agg adds a space after each comma), and a NULL
            -- array stays NULL while an empty one gives [].
            CASE
                WHEN bb.addresses_internal_id IS NULL THEN NULL
                ELSE (
                    SELECT to_json(COALESCE(
                        array_agg(addr.cle_interop ORDER BY link.ord),
                        '{{}}'::varchar[]
                    ))
                    FROM unnest(bb.addresses_internal_id)
                        WITH ORDINALITY AS link(internal_id, ord)
                    LEFT JOIN batid_address addr
                        ON addr.internal_id = link.internal_id
                )
            END as addresses_id,
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

    The export runs in its own thread, on its own database connection, because
    the HTTP response pulls chunks from a queue while the export streams them
    from the COPY. Django's connections are thread-local, and closing this one
    is up to us: close_old_connections only ever runs on the request thread.
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
                    with cursor.copy(
                        _build_copy_query(
                            start_ts, end_ts, city_shape_wkt, with_header=first_slice
                        )
                    ) as copy:
                        for data in copy:
                            writer.write(data)
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
                    "Liste l'ensemble des modifications apportées au RNB depuis une date donnée, sous forme de fichier CSV. "
                    "Chaque ligne correspond à une version d'un bâtiment. Voici les points importants à retenir : <br />"
                    "<ul>"
                    "<li>Les modifications sont triées par date de modification croissante.</li>"
                    "<li>Un même bâtiment peut apparaître plusieurs fois dans la période considérée. Par exemple, une création (`create`) suivie d'une mise à jour (`update`). Appliquez les lignes dans l'ordre du fichier.</li>"
                    "<li>La colonne `action` indique l'opération à mener sur une base locale pour la garder synchronisée avec le RNB. Il existe 4 actions : `create`, `update`, `deactivate` et `reactivate`.</li>"
                    "<li>La colonne `event_type` indique l'opération réalisée sur le bâtiment dans le RNB. Les lignes produites par une même opération partagent le même `event_id`.</li>"
                    "</ul>"
                    "Correspondance entre `event_type` et `action` :"
                    "<ul>"
                    "<li>`creation` (création d'un bâtiment) : `create`</li>"
                    "<li>`update` (modification d'un bâtiment, y compris un changement de statut comme une démolition) : `update`</li>"
                    "<li>`deactivation` (désactivation d'un identifiant ne correspondant pas à un bâtiment) : `deactivate`</li>"
                    "<li>`reactivation` (réactivation d'un identifiant désactivé) : `reactivate`</li>"
                    "<li>`merge` (fusion de plusieurs bâtiments en un seul) : `deactivate` pour les bâtiments parents, `create` pour le bâtiment issu de la fusion</li>"
                    "<li>`split` (scission d'un bâtiment en plusieurs) : `deactivate` pour le bâtiment parent, `create` pour les bâtiments issus de la scission</li>"
                    "<li>`revert_creation` (annulation d'une création) : `deactivate`</li>"
                    "<li>`revert_update` (annulation d'une modification, le bâtiment retrouve ses valeurs précédentes) : `update`</li>"
                    "<li>`revert_merge` (annulation d'une fusion) : `deactivate` pour le bâtiment issu de la fusion, `reactivate` pour les bâtiments parents</li>"
                    "<li>`revert_split` (annulation d'une scission) : `deactivate` pour les bâtiments issus de la scission, `reactivate` pour le bâtiment parent</li>"
                    "</ul>"
                    "Par exemple, une fusion de deux bâtiments fait apparaître 3 lignes avec l'`event_type` `merge` et le même `event_id` : "
                    "les deux bâtiments parents ont l'action `deactivate` et le bâtiment issu de la fusion a l'action `create`. "
                    "Ce dernier liste les identifiants des parents dans la colonne `parent_buildings`.<br /><br />"
                    "Format des colonnes :"
                    "<ul>"
                    "<li>`action` : action à mener (voir ci-dessus)</li>"
                    "<li>`rnb_id` : identifiant RNB du bâtiment</li>"
                    "<li>`status` : statut du bâtiment (`constructed`, `notUsable` ou `demolished`)</li>"
                    "<li>`is_active` : `1` si l'identifiant est actif, `0` s'il est désactivé</li>"
                    '<li>`sys_period` : période de validité de cette version, au format plage de dates PostgreSQL : `["début","fin")`, ou `["début",)` pour la version courante. La date de début est la date de la modification</li>'
                    "<li>`point` : point représentatif du bâtiment au format EWKT, en WGS84 (ex : `SRID=4326;POINT(2.35 48.85)`)</li>"
                    "<li>`shape` : géométrie du bâtiment au format EWKT, en WGS84 (point, polygone ou multipolygone)</li>"
                    "<li>`addresses_id` : tableau JSON des clés d'interopérabilité BAN des adresses du bâtiment. Vide ou `[]` si le bâtiment n'a pas d'adresse</li>"
                    '<li>`ext_ids` : identifiants du bâtiment dans d\'autres bases (BD Topo, BDNB…), sous forme de tableau JSON d\'objets `{"id", "source", "source_version", "created_at"}`. Vaut `[]` s\'il n\'y en a pas</li>'
                    "<li>`parent_buildings` : tableau JSON des identifiants RNB des bâtiments dont est issu ce bâtiment (fusion, scission). Vide si le bâtiment n'est issu d'aucune fusion ou scission</li>"
                    "<li>`event_id` : identifiant (UUID) de l'opération</li>"
                    "<li>`event_type` : type d'opération (voir ci-dessus)</li>"
                    "<li>`username` : nom de l'utilisateur à l'origine de l'opération. Vaut `RNB` pour les imports, rattachés au compte de l'équipe</li>"
                    "<li>`user_organization_name` : nom de l'organisation de cet utilisateur. Vide s'il n'en a pas</li>"
                    "<li>`user_organization_id` : identifiant de l'organisation de cet utilisateur. Vide s'il n'en a pas</li>"
                    '<li>`validated_by` : tableau JSON des utilisateurs ayant validé le bâtiment, chacun sous la forme `{"id", "username", "organization_name", "organization_short_name"}`. Vaut `[]` s\'il n\'y en a pas</li>'
                    "</ul>"
                    f"Exemple de requête : `https://rnb-api.beta.gouv.fr/api/alpha/buildings/diff/?since={SINCE_EXAMPLE}`"
                ),
                "operationId": "getDiff",
                "parameters": [
                    {
                        "name": "since",
                        "in": "query",
                        "description": (
                            "Date et heure à partir de laquelle les modifications sont retournées. Le format est ISO 8601. <br />"
                            f"Cette date ne doit pas être antérieure aux {MAX_DIFF_DAYS} derniers jours. "
                            "Si aucune modification du RNB n'est postérieure à cette date, le fichier est vide, sans en-tête.<br/>"
                            "Pour récupérer le RNB dans son intégralité, téléchargez la base de données (l'ensemble de la base est <a href='https://www.data.gouv.fr/fr/datasets/referentiel-national-des-batiments/'>disponible ici</a>). "
                        ),
                        "required": True,
                        "schema": {"type": "string", "format": "date-time"},
                        "example": SINCE_EXAMPLE,
                    },
                    {
                        "name": "insee_code",
                        "in": "query",
                        "description": (
                            "Code INSEE de la commune pour filtrer les modifications du RNB. "
                            "Seules les modifications de bâtiments dont le point (localisation) "
                            "intersecte la commune seront retournées. Le code INSEE est composé "
                            "de 5 caractères."
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
                    },
                    "400": {
                        "description": (
                            f"Le paramètre `since` est absent, mal formaté, n'est pas une date existante ou est antérieur aux {MAX_DIFF_DAYS} derniers jours. "
                            "Le corps de la réponse est une phrase, pas un objet JSON."
                        ),
                    },
                    "404": {
                        "description": (
                            "Le code INSEE indiqué ne correspond à aucune commune. "
                            "Le corps de la réponse est une phrase, pas un objet JSON."
                        ),
                    },
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
        try:
            since = parse_datetime(since_input)
            if since is not None and since.tzinfo is None:
                since = since.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            # well formatted but not a real date, e.g. 2026-02-30
            since = None
        last_available_modification = datetime.now(timezone.utc) - timedelta(
            days=MAX_DIFF_DAYS
        )

        if since is None:
            return HttpResponse(
                "The 'since' parameter is missing or incorrect", status=400
            )

        # nobody should download the whole database
        if since < last_available_modification:
            return HttpResponse(
                f"Maximum diff period is currently {MAX_DIFF_DAYS} days ({last_available_modification}). Please let us know if you need more.",
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
