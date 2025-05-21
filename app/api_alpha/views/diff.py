class DiffView(APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Différences depuis une date donnée",
                "description": (
                    "Liste l'ensemble des modifications apportées au RNB depuis une date données. Génère un fichier CSV. Voici les points importants à retenir : <br />"
                    "<ul>"
                    "<li>Les modifications listées sont de trois types : create, update et delete</li>"
                    "<li>Les modifications sont triées par date de modification croissante</li>"
                    "<li>Il est possible qu'un même bâtiment ait plusieurs modifications dans la période considérée. Par exemple, une création (create) suivie d'une mise à jour (update)</li>"
                    "</ul>"
                ),
                "operationId": "getDiff",
                "parameters": [
                    {
                        "name": "since",
                        "in": "query",
                        "description": (
                            "Date et heure à partir de laquelle les modifications sont retournées. Le format est ISO 8601. <br />"
                            "Seules les dates après le 1er avril 2024 sont acceptées.<br/>"
                            "Une date antérieure reviendrait à télécharger l'intégralité de la base de données (l'ensemble de la base est <a href='https://www.data.gouv.fr/fr/datasets/referentiel-national-des-batiments/'>disponible ici</a>). "
                        ),
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "2024-04-02T00:00:00Z",
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Fichier CSV listant l'ensemble des opérations ayant modifié le RNB depuis la date indiquée.",
                        "content": {
                            "text/csv": {
                                "schema": {"type": "string"},
                                "example": (
                                    "action,rnb_id,status,sys_period,point,shape,addresses_id,ext_ids"
                                ),
                            }
                        },
                    }
                },
            }
        }
    )
    def get(self, request):

        # Alternative idea:
        # In case the streaming solution becomes a problem (might be because of the process fork or any other reason), here is another idea for avoiding relying too heavily on the database:
        # Since the list of modifications between two dates is static, we could precalculate large time chunks (eg: one each month) and save those results in CSV files. When the diff endpoint is requested, we could assemble some of those large CSV chunks into one, add remaining rows to complete the time period by fetching them from db and finally serve the combined file.

        since_input = request.GET.get("since", "")
        # parse since to a timestamp
        since = parse_datetime(since_input)
        if since is None:
            return HttpResponse(
                "The 'since' parameter is missing or incorrect", status=400
            )
        # nobody should download the whole database
        elif since < parse_datetime("2024-04-01T00:00:00Z"):
            return HttpResponse(
                "The 'since' parameter must be after 2024-04-01T00:00:00Z",
                status=400,
            )

        with connection.cursor() as cursor:
            most_recent_modification_query = sql.SQL(
                """
                select max(lower(sys_period)) from batid_building_with_history
                """
            )
            cursor.execute(most_recent_modification_query)
            most_recent_modification = cursor.fetchone()[0]

        # file descriptors r, w for reading and writing
        r, w = os.pipe()
        # the process is forked
        # would it be possible to avoid creating a new process
        # and keep the streaming feature?
        # https://stackoverflow.com/questions/78998534/stream-data-from-postgres-to-http-request-using-django-streaminghttpresponse?noredirect=1#comment139290268_78998534
        processid = os.fork()

        if processid:
            # This is the parent process
            # the parent will only read data coming from the child process, we can close w
            os.close(w)
            # data coming from the child process arrives here
            r = os.fdopen(r)
            return StreamingHttpResponse(
                r,
                content_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="diff_{since.isoformat()}_{most_recent_modification.isoformat()}.csv"'
                },
            )
        else:
            # This is the child process
            # the child will only write data, we can close r
            os.close(r)
            w = os.fdopen(w, "w")

            with connection.cursor() as cursor:
                start_ts = since
                first_query = True

                while start_ts < most_recent_modification:
                    end_ts = start_ts + timedelta(days=1)

                    raw_sql = """
                        COPY (
                            select
                            CASE
                                WHEN event_type = 'delete' THEN 'deactivate'
                                WHEN event_type = 'deactivation' THEN 'deactivate'
                                WHEN event_type = 'update' THEN 'update'
                                WHEN event_type = 'split' and not is_active THEN 'deactivate'
                                WHEN event_type = 'split' and is_active THEN 'create'
                                WHEN event_type = 'merge' and not is_active THEN 'deactivate'
                                WHEN event_type = 'merge' and is_active THEN 'create'
                                ELSE 'create'
                            END as action,
                            rnb_id,
                            status,
                            is_active::int,
                            sys_period,
                            ST_AsEWKT(point) as point,
                            ST_AsEWKT(shape) as shape,
                            to_json(addresses_id) as addresses_id,
                            COALESCE(ext_ids, '[]'::jsonb) as ext_ids,
                            parent_buildings,
                            event_id,
                            event_type
                            FROM batid_building_with_history bb
                            where lower(sys_period) > {start}::timestamp with time zone and lower(sys_period) <= {end}::timestamp with time zone
                            order by lower(sys_period)
                        ) TO STDOUT WITH CSV
                        """

                    if first_query:
                        raw_sql = raw_sql + " HEADER"
                        first_query = False

                    sql_query = sql.SQL(raw_sql).format(
                        start=sql.Literal(start_ts.isoformat()),
                        end=sql.Literal(end_ts.isoformat()),
                    )
                    # the data coming from the query is streamed to the file descriptor w
                    # and will be received by the parent process as a stream
                    cursor.copy_expert(sql_query, w)
                    start_ts = end_ts
            w.close()
            # the child process is terminated
            os._exit(0)
