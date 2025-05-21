class BuildingGuessView(RNBLoggingMixin, APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Identification de bâtiment",
                "description": (
                    "Cet endpoint permet d'identifier le bâtiment correspondant à une série de critères. Il permet d'accueillir des données imprécises et tente de les combiner pour fournir le meilleur résultat. NB : l'URL se termine nécessairement par un slash (/)."
                ),
                "operationId": "guessBuilding",
                "parameters": [
                    {
                        "name": "address",
                        "in": "query",
                        "description": "Adresse du bâtiment",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "1 rue de la paix, Mérignac",
                    },
                    {
                        "name": "point",
                        "in": "query",
                        "description": "Coordonnées GPS du bâtiment. Format : <code>lat,lng</code>.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "44.84114313595151,-0.5705289444867035",
                    },
                    {
                        "name": "name",
                        "in": "query",
                        "description": "Nom du bâtiment. Est transmis à un géocoder OSM (<a href='https://github.com/komoot/photon'>Photon</a>).",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "Notre Dame de Paris",
                    },
                    {
                        "name": "page",
                        "in": "query",
                        "description": "Numéro de page pour la pagination",
                        "required": False,
                        "schema": {"type": "integer"},
                        "example": 1,
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste des bâtiments identifiés triés par score descendant.",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "items": {
                                        "allOf": [
                                            {"$ref": "#/components/schemas/Building"},
                                            {
                                                "type": "object",
                                                "properties": {
                                                    "score": {
                                                        "type": "number",
                                                        "description": "Score de correspondance entre la requête et le bâtiment",
                                                        "example": 0.8,
                                                    },
                                                    "sub_scores": {
                                                        "type": "object",
                                                        "description": "Liste des scores intermédiaires. Leur somme est égale au score principal.",
                                                    },
                                                },
                                            },
                                        ]
                                    },
                                    "type": "array",
                                }
                            }
                        },
                    }
                },
            }
        }
    )
    def get(self, request, *args, **kwargs):
        search = BuildingGuess()
        search.set_params_from_url(**request.query_params.dict())

        if not search.is_valid():
            return Response(
                {"errors": search.errors}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            qs = search.get_queryset()
            serializer = GuessBuildingSerializer(qs, many=True)

            return Response(serializer.data)
        except BANAPIDown:
            raise ServiceUnavailable(detail="BAN API is currently down")


class BuildingClosestView(RNBLoggingMixin, APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Bâtiments les plus proches d'un point",
                "description": "Cet endpoint permet d'obtenir une liste paginée des bâtiments présents dans un rayon donné autour d'un point donné. Les bâtiments sont triés par distance croissante par rapport au point donné. NB : l'URL se termine nécessairement par un slash (/).",
                "operationId": "closestBuildings",
                "parameters": [
                    {
                        "name": "point",
                        "in": "query",
                        "description": "Latitude et longitude, séparées par une virgule, du point de recherche.",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "44.8201164915397,-0.5717449803671368",
                    },
                    {
                        "name": "radius",
                        "in": "query",
                        "description": "Rayon de recherche en mètres, autour du point. Compris entre 0 et 1000 mètres.",
                        "required": True,
                        "schema": {"type": "integer"},
                        "example": 1000,
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste paginée des bâtiments les plus proches du point donné",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "next": {
                                            "type": "string",
                                            "description": "URL de la page de résultats suivante",
                                            "nullable": True,
                                        },
                                        "previous": {
                                            "type": "string",
                                            "description": "URL de la page de résultats précédente",
                                            "nullable": True,
                                        },
                                        "results": {
                                            "type": "array",
                                            "items": {
                                                "allOf": [
                                                    {
                                                        "$ref": "#/components/schemas/Building"
                                                    },
                                                    {
                                                        "type": "object",
                                                        "properties": {
                                                            "distance": {
                                                                "type": "number",
                                                                "format": "float",
                                                                "example": 6.78,
                                                                "description": "Distance en mètres entre le bâtiment et le point donné",
                                                            },
                                                        },
                                                    },
                                                ]
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
    )
    def get(self, request, *args, **kwargs):
        query_serializer = BuildingClosestQuerySerializer(data=request.query_params)

        if query_serializer.is_valid():

            point = request.query_params.get("point")
            radius = request.query_params.get("radius")
            lat, lng = point.split(",")
            lat = float(lat)
            lng = float(lng)
            radius = int(radius)

            # Get results and paginate
            bdgs = get_closest_from_point(lat, lng, radius)
            paginator = BuildingCursorPagination()
            paginated_bdgs = paginator.paginate_queryset(bdgs, request)
            serializer = BuildingClosestSerializer(paginated_bdgs, many=True)

            return paginator.get_paginated_response(serializer.data)

        else:
            # Invalid data, return validation errors
            return Response(query_serializer.errors, status=400)


class BuildingPlotView(RNBLoggingMixin, APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Bâtiments sur une parcelle cadastrale",
                "description": "Cet endpoint permet d'obtenir une liste paginée des bâtiments présents sur une parcelle cadastrale. Les bâtiments sont triés par taux de recouvrement décroissant entre le bâtiment et la parcelle (le bâtiment entièrement sur une parcelle arrive avant celui à moitié sur la parcelle). La méthode de filtrage est purement géométrique et ne tient pas compte du lien fiscal entre le bâtiment et la parcelle. Des faux positifs sont donc possibles. NB : l'URL se termine nécessairement par un slash (/).",
                "operationId": "plotBuildings",
                "parameters": [
                    {
                        "name": "plot_id",
                        "in": "path",
                        "description": "Identifiant de la parcelle cadastrale.",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "01402000AB0051",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste paginée des bâtiments présents sur la parcelle cadastrale",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "next": {
                                            "type": "string",
                                            "description": "URL de la page de résultats suivante",
                                            "nullable": True,
                                        },
                                        "previous": {
                                            "type": "string",
                                            "description": "URL de la page de résultats précédente",
                                            "nullable": True,
                                        },
                                        "results": {
                                            "type": "array",
                                            "items": {
                                                "allOf": [
                                                    {
                                                        "$ref": "#/components/schemas/Building"
                                                    },
                                                    {
                                                        "type": "number",
                                                        "name": "bdg_cover_ratio",
                                                        "description": "Taux d'intersection entre le bâtiment et la parcelle. Ce taux est compris entre 0 et 1. Un taux de 1 signifie que la parcelle couvre entièrement le bâtiment.",
                                                        "example": 0.65,
                                                    },
                                                ]
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
    )
    def get(self, request, plot_id, *args, **kwargs):
        try:
            bdgs = get_buildings_on_plot(plot_id)
        except PlotUnknown:
            raise NotFound("Plot unknown")

        paginator = BuildingCursorPagination()
        paginated_bdgs = paginator.paginate_queryset(bdgs, request)
        serializer = BuildingPlotSerializer(paginated_bdgs, many=True)

        return paginator.get_paginated_response(serializer.data)


class BuildingAddressView(RNBLoggingMixin, APIView):
    @rnb_doc(
        {
            "get": {
                "summary": "Identification de bâtiments par leur adresse",
                "description": "Cet endpoint permet d'obtenir une liste paginée des bâtiments associés à une adresse. NB : l'URL se termine nécessairement par un slash (/).",
                "operationId": "address",
                "parameters": [
                    {
                        "name": "q",
                        "in": "query",
                        "description": "Adresse texte non structurée. L'adresse fournie est recherchée dans la BAN afin de récupérer la clé d'interopérabilité associée. C'est via cette clé que sont filtrés les bâtiments. Si le geocodage échoue aucun résultat n'est renvoyé et le champ **status** de la réponse contient **geocoding_no_result**",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "4 rue scipion, 75005 Paris",
                    },
                    {
                        "name": "min_score",
                        "in": "query",
                        "description": "Score minimal attendu du géocodage BAN. Valeur par défaut : **0.8**. Si le score est strictement inférieur à cette limite, aucun résultat n'est renvoyé et le champ **status** de la réponse contient **geocoding_score_is_too_low**",
                        "required": False,
                        "schema": {"type": "float"},
                        "example": "0.9",
                    },
                    {
                        "name": "cle_interop_ban",
                        "in": "query",
                        "description": "Clé d'interopérabilité BAN. Si vous êtes en possession d'une clé d'interoperabilité, il est plus efficace de faire une recherche grâce à elle que via une adresse textuelle.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "75105_8884_00004",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste paginée des bâtiments associés à l'adresse donnée.",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "next": {
                                            "type": "string",
                                            "description": "URL de la page de résultats suivante",
                                            "nullable": True,
                                        },
                                        "previous": {
                                            "type": "string",
                                            "description": "URL de la page de résultats précédente",
                                            "nullable": True,
                                        },
                                        "cle_interop_ban": {
                                            "type": "string",
                                            "description": "Clé d'interopérabilité BAN utilisée pour lister les bâtiments",
                                            "nullable": True,
                                        },
                                        "status": {
                                            "type": "string",
                                            "description": "'geocoding_score_is_too_low' si le géocodage BAN renvoie un score inférieur à 'min_score'. 'geocoding_no_result' si le géocodage ne renvoie pas de résultats. 'ok' sinon",
                                            "nullable": False,
                                        },
                                        "score_ban": {
                                            "type": "float",
                                            "description": "Si un géocodage a lieu, renvoie le score du meilleur résultat, celui utilisé pour lister les bâtiments. Ce score doit être supérieur à 'min_score' pour que des bâtiments soient renvoyés.",
                                            "nullable": False,
                                        },
                                        "results": {
                                            "type": "array",
                                            "nullable": True,
                                            "items": {
                                                "$ref": "#/components/schemas/Building"
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
    )
    def get(self, request, *args, **kwargs):
        query_serializer = BuildingAddressQuerySerializer(data=request.query_params)
        infos: dict[str, Any] = {
            "cle_interop_ban": None,
            "score_ban": None,
            "status": None,
        }

        if query_serializer.is_valid():
            q = request.query_params.get("q")
            paginator = BuildingAddressCursorPagination()

            if q:
                # 0.8 is the default value
                min_score = float(request.query_params.get("min_score", 0.8))
                geocoder = BanGeocoder()
                try:
                    best_result = geocoder.cle_interop_ban_best_result({"q": q})
                except BANAPIDown:
                    raise ServiceUnavailable(detail="BAN API is currently down")
                cle_interop_ban = best_result["cle_interop_ban"]
                score = best_result["score"]

                infos["cle_interop_ban"] = cle_interop_ban
                infos["score_ban"] = score

                if cle_interop_ban is None:
                    infos["status"] = "geocoding_no_result"
                    return paginator.get_paginated_response(None, infos)
                if score is not None and score < min_score:
                    infos["status"] = "geocoding_score_is_too_low"
                    return paginator.get_paginated_response(None, infos)
            else:
                cle_interop_ban = request.query_params.get("cle_interop_ban")
                infos["cle_interop_ban"] = cle_interop_ban

            infos["status"] = "ok"
            buildings = (
                Building.objects.filter(is_active=True)
                .filter(addresses_read_only__id=cle_interop_ban)
                .prefetch_related("addresses_read_only")
            )
            paginated_bdgs = paginator.paginate_queryset(buildings, request)
            serialized_buildings = BuildingSerializer(paginated_bdgs, many=True)

            return paginator.get_paginated_response(serialized_buildings.data, infos)
        else:
            # Invalid data, return validation errors
            return Response(query_serializer.errors, status=400)


class BuildingCursorPagination(BasePagination):
    page_size = 20

    cursor_query_param = "cursor"

    def __init__(self):
        self.base_url = None
        self.current_page = None

        self.has_next = False
        self.has_previous = False

        self.page = None

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "next": {
                    "type": "string",
                    "nullable": True,
                },
                "previous": {
                    "type": "string",
                    "nullable": True,
                },
                "results": schema,
            },
        }

    def get_html_context(self):
        return {
            "previous_url": self.get_previous_link(),
            "next_url": self.get_next_link(),
        }

    def get_paginated_response(self, data):

        return Response(
            {
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def get_next_link(self):

        if self.has_next:
            next_cursor = str(self.current_page + 1)
            return replace_query_param(
                self.base_url, self.cursor_query_param, next_cursor
            )

        return None

    def get_previous_link(self):

        if self.has_previous:
            previous_cursor = str(self.current_page - 1)
            return replace_query_param(
                self.base_url, self.cursor_query_param, previous_cursor
            )

        return None

    def paginate_queryset(self, queryset, request, view=None):

        # Get the current URL with all parameters
        self.base_url = request.build_absolute_uri()

        self.current_page = self.get_page(request)
        if self.current_page is None:
            self.current_page = 1

        offset = (self.current_page - 1) * self.page_size

        # If we have an offset cursor then offset the entire page by that amount.
        # We also always fetch an extra item in order to determine if there is a
        # page following on from this one.
        results = queryset[offset : offset + self.page_size + 1]

        if len(results) > self.page_size:
            self.has_next = True

        if self.current_page > 1:
            self.has_previous = True

        return results[: self.page_size]

    def get_page(self, request):

        request_page = request.query_params.get(self.cursor_query_param)
        if request_page:
            try:
                return int(request_page)
            except ValueError:
                return None

        return None

    def encode_cursor(self, cursor):

        return b64encode(cursor.encode("ascii")).decode("ascii")


class BuildingAddressCursorPagination(BuildingCursorPagination):
    def get_paginated_response(self, data, infos):
        return Response(
            {
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "status": infos["status"],
                "cle_interop_ban": infos["cle_interop_ban"],
                "score_ban": infos["score_ban"],
                "results": data,
            }
        )


class ListCreateBuildings(RNBLoggingMixin, APIView):
    permission_classes = [ReadOnly | RNBContributorPermission]

    @rnb_doc(
        {
            "get": {
                "summary": "Liste des batiments",
                "description": (
                    "Cet endpoint permet de récupérer une liste paginée de bâtiments. "
                    "Des filtres, notamment par code INSEE de la commune, sont disponibles. NB : l'URL se termine nécessairement par un slash (/)."
                ),
                "operationId": "listBuildings",
                "parameters": [
                    {
                        "name": "insee_code",
                        "in": "query",
                        "description": "Filtre les bâtiments dont l'emprise au sol est située dans les limites géographiques de la commune ayant ce code INSEE.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "75101",
                    },
                    {
                        "name": "status",
                        "in": "query",
                        "description": f"Filtre les bâtiments par statut. Il est possible d'utiliser plusieurs valeurs séparées par des virgules. Les valeurs possibles sont : <br /><br /> {get_status_html_list()}<br />",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "constructed,demolished",
                    },
                    {
                        "name": "cle_interop_ban",
                        "in": "query",
                        "description": "Filtre les bâtiments associés à cette clé d'interopérabilité BAN.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "94067_7115_00073",
                    },
                    {
                        "name": "bb",
                        "in": "query",
                        "description": (
                            "Filtre les bâtiments dont l'emprise au sol est située dans la bounding box"
                            "définie par les coordonnées Nord-Ouest et Sud-Est. Les coordonnées sont séparées par des virgules. "
                            "Le format est <code>nw_lat,nw_lng,se_lat,se_lng</code> où : <br/>"
                            "<ul>"
                            "<li><b>nw_lat</b> : latitude du point Nord Ouest de la bounding box</li>"
                            "<li><b>nw_lng</b> : longitude du point Nord Ouest de la bounding box</li>"
                            "<li><b>se_lat</b> : latitude du point Sud Est de la bounding box</li>"
                            "<li><b>se_lng</b> : longitude du point Sud Est de la bounding box</li>"
                            "</ul><br />"
                        ),
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "48.845782,2.424525,48.839201,2.434158",
                    },
                    {
                        "name": "withPlots",
                        "in": "query",
                        "description": "Inclure les parcelles intersectant les bâtiments de la réponse. Valeur attendue : 1. Chaque parcelle associée intersecte le bâtiment correspondant. Elle contient son identifiant ainsi que le taux de couverture du bâtiment.",
                        "required": False,
                        "schema": {
                            "type": "boolean",
                            "default": False,
                        },
                        "example": "1",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Liste paginée de bâtiments",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "next": {
                                            "type": "string",
                                            "description": "<br />URL de la page de résultats suivante<br />",
                                            "nullable": True,
                                            "example": f"{settings.URL}/api/alpha/buildings/?cursor=cD02MzQ3OTk1",
                                        },
                                        "previous": {
                                            "type": "string",
                                            "description": "<br />URL de la page de résultats précédente<br />",
                                            "nullable": True,
                                            "example": f"{settings.URL}/api/alpha/buildings/?cursor=hFG78YEdFR",
                                        },
                                        "results": {
                                            "type": "array",
                                            "items": {
                                                "allOf": [
                                                    {
                                                        "$ref": "#/components/schemas/Building"
                                                    },
                                                    {
                                                        "$ref": "#/components/schemas/BuildingWPlots"
                                                    },
                                                ]
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            },
        },
    )
    def get(self, request):
        query_params = request.query_params.dict()

        # check if we need to include plots
        with_plots_param = request.query_params.get("withPlots", None)
        with_plots = True if with_plots_param == "1" else False
        query_params["with_plots"] = with_plots

        # add user to query params
        query_params["user"] = request.user
        buildings = list_bdgs(query_params)
        paginator = BuildingCursorPagination()

        # paginate
        paginated_buildings = paginator.paginate_queryset(buildings, request)
        serializer = BuildingSerializer(
            paginated_buildings, with_plots=with_plots, many=True
        )

        return paginator.get_paginated_response(serializer.data)

    @rnb_doc(
        {
            "post": {
                "summary": "Création d'un bâtiment",
                "description": "Cet endpoint permet de créer un bâtiment dans le RNB. Lors de la création, un identifiant RNB (ID-RNB) est généré. L'utilisateur doit être identifié et disposer des droits nécessaires pour écrire dans le RNB.",
                "operationId": "postBuilding",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "comment": {
                                        "type": "string",
                                        "description": "Commentaire optionnel associé à la création du bâtiment.",
                                        "example": "Bâtiment ajouté suite à une nouvelle construction, visible sur la vue satellite.",
                                    },
                                    "status": {
                                        "type": "string",
                                        "enum": get_status_list(),
                                        "description": "Statut du bâtiment.",
                                        "example": "constructed",
                                    },
                                    "addresses_cle_interop": {
                                        "type": "array",
                                        # currently a bug in gitbook, addding info on items hides the description
                                        # "items": {"type": "string"},
                                        "description": "Liste des clés d'interopérabilité BAN liées au bâtiment.",
                                        "example": [
                                            "75105_8884_00004",
                                            "75105_8884_00006",
                                        ],
                                    },
                                    "shape": {
                                        "type": "string",
                                        "description": "Géométrie du bâtiment au format WKT ou HEX, en WGS84. La géométrie attendue est idéalement un polygone représentant le bâtiment, mais il est également possible de ne donner qu'un point.",
                                        "example": "POLYGON((2.3522 48.8566, 2.3532 48.8567, 2.3528 48.857, 2.3522 48.8566))",
                                    },
                                },
                                "required": ["status", "shape"],
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Détails du bâtiment nouvellement créé dans le RNB",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "allOf": [
                                        {"$ref": "#/components/schemas/Building"},
                                        {"$ref": "#/components/schemas/BuildingWPlots"},
                                    ]
                                }
                            }
                        },
                    },
                    "403": {
                        "description": "L'utilisateur n'a pas les droits nécessaires pour créer un bâtiment."
                    },
                    "503": {"description": "Service temporairement indisponible"},
                    "404": {
                        "description": "Une clé d'interopérabilité n'a pas été trouvée auprès de la BAN"
                    },
                },
            }
        }
    )
    def post(self, request):
        serializer = BuildingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.data
        user = request.user

        with transaction.atomic():
            # create a contribution
            contribution = Contribution(
                text=data.get("comment"),
                status="fixed",
                status_changed_at=datetime.now(timezone.utc),
                report=False,
                review_user=user,
            )
            contribution.save()

            event_origin = {
                "source": "contribution",
                "contribution_id": contribution.id,
            }

            status = data.get("status")
            addresses_cle_interop = data.get("addresses_cle_interop")
            shape = GEOSGeometry(data.get("shape"))

            try:
                created_building = Building.create_new(
                    user=user,
                    event_origin=event_origin,
                    status=status,
                    addresses_id=addresses_cle_interop,
                    shape=shape,
                    ext_ids=[],
                )
            except BANAPIDown:
                raise ServiceUnavailable(detail="BAN API is currently down")
            except BANUnknownCleInterop:
                raise NotFound(detail="Cle d'intéropérabilité not found on the BAN API")
            except BANBadResultType:
                raise BadRequest(
                    detail="BAN result has not the expected type (must be 'numero')"
                )
            except InvalidWGS84Geometry:
                raise BadRequest(
                    detail="Provided shape is invalid (bad topology or wrong CRS)"
                )
            except BuildingTooLarge:
                raise BadRequest(
                    detail="Building area too large. Maximum allowed: 500000m²"
                )

            # update the contribution now that the rnb_id is known
            contribution.rnb_id = created_building.rnb_id
            contribution.save()

        serializer = BuildingSerializer(created_building, with_plots=True)
        return Response(serializer.data, status=http_status.HTTP_201_CREATED)


class MergeBuildings(APIView):
    permission_classes = [RNBContributorPermission]

    @rnb_doc(
        {
            "post": {
                "summary": "Fusion de bâtiments",
                "description": LiteralStr(
                    """\
Permet de corriger le RNB en fusionnant plusieurs bâtiments existants, donnant lieu à la création d'un nouveau bâtiment.

Cet endpoint nécessite d'être identifié et d'avoir des droits d'édition du RNB.
                """
                ),
                "operationId": "mergeBuildings",
                "parameters": [],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "comment": {
                                        "type": "string",
                                        "description": """Commentaire optionnel associé à l'opération""",
                                    },
                                    "rnb_ids": {
                                        "type": "array",
                                        "description": "Liste des ID-RNB des bâtiments à fusionner",
                                        "exemple": ["XXXXYYYYZZZZ", "AAAABBBBCCCC"],
                                    },
                                    "merge_existing_addresses": {
                                        "type": "bool",
                                        "description": LiteralStr(
                                            """\
- `True`, le bâtiment nouvellement créé hérite des adresses des bâtiments dont il est issu.
- `False` ou non rempli, le champ `addresses_cle_interop` est utilisé pour déterminer les adresses du bâtiment."""
                                        ),
                                    },
                                    "addresses_cle_interop": {
                                        "type": "array",
                                        "description": "Liste des clés d'interopérabilité BAN liées au nouveau bâtiment créé. Si une liste vide est passée, le bâtiment ne sera lié à aucune adresse.",
                                        "exemple": [
                                            "75105_8884_00004",
                                            "75105_8884_00006",
                                        ],
                                    },
                                    "status": {
                                        "type": "string",
                                        "enum": get_status_list(),
                                        "description": "Statut du bâtiment.",
                                        "example": "constructed",
                                    },
                                },
                                "required": ["rnb_ids", "status"],
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Détails du bâtiment nouvellement créé",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "allOf": [
                                        {"$ref": "#/components/schemas/Building"},
                                    ]
                                }
                            }
                        },
                    },
                    "403": {
                        "description": "L'utilisateur n'a pas les droits nécessaires pour créer un bâtiment."
                    },
                    "503": {"description": "Service temporairement indisponible"},
                    "404": {
                        "description": "ID-RNB inconnu ou une clé d'interopérabilité n'a pas été trouvée auprès de la BAN"
                    },
                },
            }
        }
    )
    def post(self, request):
        serializer = BuildingMergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.data
        user = request.user

        with transaction.atomic():
            contribution = Contribution(
                text=data.get("comment"),
                status="fixed",
                status_changed_at=datetime.now(timezone.utc),
                report=False,
                review_user=user,
            )
            contribution.save()

            event_origin = {
                "source": "contribution",
                "contribution_id": contribution.id,
            }

            rnb_ids = data.get("rnb_ids")
            buildings = []
            for rnb_id in rnb_ids:
                building = get_object_or_404(Building, rnb_id=rnb_id)
                buildings.append(building)

            status = data.get("status")

            merge_existing_addresses = data.get("merge_existing_addresses")
            if merge_existing_addresses:
                addresses_id = [
                    address
                    for building in buildings
                    for address in building.addresses_id
                ]
            else:
                addresses_id = data.get("addresses_cle_interop")

            # remove possible duplicates
            addresses_id = list(set(addresses_id))

            try:
                new_building = Building.merge(
                    buildings, user, event_origin, status, addresses_id
                )
            except BANAPIDown:
                raise ServiceUnavailable(detail="BAN API is currently down")
            except BANUnknownCleInterop:
                raise NotFound(detail="Cle d'intéropérabilité not found on the BAN API")
            except BANBadResultType:
                raise BadRequest(
                    detail="BAN result has not the expected type (must be 'numero')"
                )
            except OperationOnInactiveBuilding:
                raise BadRequest(detail="Cannot merge inactive buildings")
            except NotEnoughBuildings:
                raise BadRequest(
                    detail="A merge operation requires at least two buildings"
                )
            except ImpossibleShapeMerge:
                raise BadRequest(
                    detail="To merge buildings, their shapes must be contiguous polygons. Consider updating the buildings's shapes first."
                )

            # update the contribution now that the rnb_id is known
            contribution.rnb_id = new_building.rnb_id
            contribution.save()

        serializer = BuildingSerializer(new_building, with_plots=False)
        return Response(serializer.data, status=http_status.HTTP_201_CREATED)


class SplitBuildings(APIView):
    permission_classes = [RNBContributorPermission]

    @rnb_doc(
        {
            "post": {
                "summary": "Scission de bâtiments",
                "description": LiteralStr(
                    """\
Permet de corriger le RNB en scindant un bâtiment existant, donnant lieu à la création de plusieurs nouveaux bâtiments.

Cet endpoint nécessite d'être identifié et d'avoir des droits d'édition du RNB."""
                ),
                "operationId": "splitBuildings",
                "parameters": [
                    {
                        "name": "rnb_id",
                        "in": "path",
                        "description": "Identifiant unique du bâtiment dans le RNB (ID-RNB)",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "PG46YY6YWCX8",
                    },
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "comment": {
                                        "type": "string",
                                        "description": """Commentaire optionnel associé à l'opération""",
                                    },
                                    "created_buildings": {
                                        "type": "array",
                                        "description": "Liste des bâtiments issus de la scission.",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "status": {
                                                    "type": "string",
                                                    "enum": get_status_list(),
                                                    "description": "Statut du bâtiment.",
                                                    "example": "constructed",
                                                },
                                                "shape": {
                                                    "type": "string",
                                                    "description": "Géométrie du bâtiment au format WKT ou HEX, en WGS84.",
                                                    "example": "POLYGON((2.3522 48.8566, 2.3532 48.8567, 2.3528 48.857, 2.3522 48.8566))",
                                                },
                                                "addresses_cle_interop": {
                                                    "type": "array",
                                                    "description": "Liste des clés interopérables des adresses associées",
                                                    # "items": {"type": "string"},
                                                    "example": [
                                                        "75105_8884_00004",
                                                        "75105_8884_00006",
                                                    ],
                                                },
                                            },
                                            "required": [
                                                "status",
                                                "shape",
                                                "addresses_cle_interop",
                                            ],
                                        },
                                    },
                                },
                                "required": ["rnb_id", "created_buildings"],
                            },
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Détails des bâtiments nouvellement créés",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Building"},
                                }
                            }
                        },
                    },
                    "403": {
                        "description": "L'utilisateur n'a pas les droits nécessaires pour créer un bâtiment."
                    },
                    "503": {"description": "Service temporairement indisponible"},
                    "404": {
                        "description": "ID-RNB inconnu ou une clé d'interopérabilité n'a pas été trouvée auprès de la BAN"
                    },
                },
            },
        }
    )
    def post(self, request, rnb_id):
        serializer = BuildingSplitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.data
        user = request.user

        with transaction.atomic():
            rnb_id = clean_rnb_id(rnb_id)
            comment = data.get("comment")

            contribution = Contribution(
                text=comment,
                status="fixed",
                status_changed_at=datetime.now(timezone.utc),
                report=False,
                review_user=user,
                rnb_id=rnb_id,
            )
            contribution.save()

            event_origin = {
                "source": "contribution",
                "contribution_id": contribution.id,
            }

            created_buildings: list[SplitCreatedBuilding] = data.get(
                "created_buildings"
            )

            try:
                building = get_object_or_404(Building, rnb_id=rnb_id)
                new_buildings = building.split(created_buildings, user, event_origin)
            except BANAPIDown:
                raise ServiceUnavailable(detail="BAN API is currently down")
            except BANUnknownCleInterop:
                raise NotFound(detail="Cle d'intéropérabilité not found on the BAN API")
            except BANBadResultType:
                raise BadRequest(
                    detail="BAN result has not the expected type (must be 'numero')"
                )
            except InvalidWGS84Geometry:
                raise BadRequest(
                    detail="Provided shape is invalid (bad topology or wrong CRS)"
                )
            except BuildingTooLarge:
                raise BadRequest(
                    detail="Building area too large. Maximum allowed: 500000m²"
                )
            except NotEnoughBuildings:
                raise BadRequest(
                    detail="A split operation requires at least two child buildings"
                )
            except OperationOnInactiveBuilding:
                raise BadRequest(detail="Cannot split an inactive building")

        serializer = BuildingSerializer(new_buildings, with_plots=False, many=True)
        return Response(serializer.data, status=http_status.HTTP_201_CREATED)


class SingleBuilding(APIView):
    permission_classes = [ReadOnly | RNBContributorPermission]

    @rnb_doc(
        {
            "get": {
                "summary": "Consultation d'un bâtiment",
                "description": "Cet endpoint permet de récupérer l'ensemble des attributs d'un bâtiment à partir de son identifiant RNB. NB : l'URL se termine nécessairement par un slash (/).",
                "operationId": "getBuilding",
                "parameters": [
                    {
                        "name": "rnb_id",
                        "in": "path",
                        "description": "Identifiant unique du bâtiment dans le RNB (ID-RNB)",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "PG46YY6YWCX8",
                    },
                    {
                        "name": "withPlots",
                        "in": "query",
                        "description": "Inclure les parcelles intersectant le bâtiment. Valeur attendue : 1. Chaque parcelle associée intersecte le bâtiment correspondant. Elle contient son identifiant ainsi que le taux de couverture du bâtiment par cette parcelle.",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "1",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Détails du bâtiment",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "allOf": [
                                        {"$ref": "#/components/schemas/Building"},
                                        {"$ref": "#/components/schemas/BuildingWPlots"},
                                    ]
                                }
                            }
                        },
                    }
                },
            }
        }
    )
    def get(self, request, rnb_id):

        # check if we need to include plots
        with_plots_param = request.query_params.get("withPlots", False)
        with_plots = with_plots_param == "1"

        qs = list_bdgs(
            {"user": request.user, "status": "all", "with_plots": with_plots},
            only_active=False,
        )
        building = get_object_or_404(qs, rnb_id=clean_rnb_id(rnb_id))
        serializer = BuildingSerializer(building, with_plots=with_plots)

        return Response(serializer.data)

    @rnb_doc(
        {
            "patch": {
                "summary": "Mise à jour ou désactivation/réactivation d'un bâtiment",
                "description": LiteralStr(
                    """\
Cet endpoint permet de :
* mettre à jour un bâtiment existant (status, addresses_cle_interop, shape)
* désactiver son ID-RNB s'il s'avère qu'il ne devrait pas faire partie du
  RNB. Par exemple un arbre qui aurait été par erreur répertorié comme un
  bâtiment du RNB.
* réactiver un ID-RNB, si celui-ci a été désactivé par erreur.

Il n'est pas possible de simultanément mettre à jour un bâtiment et de le désactiver/réactiver.

Cet endpoint nécessite d'être identifié et d'avoir des droits d'édition du RNB.

Exemples valides:
* ```{"comment": "faux bâtiment", "is_active": False}```
* ```{"comment": "RNB ID désactivé par erreur, on le réactive", "is_active": True}```
* ```{"comment": "bâtiment démoli", "status": "demolished"}```
* ```{"comment": "bâtiment en ruine", "status": "notUsable", "addresses_cle_interop": ["75105_8884_00004"]}```
"""
                ),
                "operationId": "patchBuilding",
                "parameters": [
                    {
                        "name": "rnb_id",
                        "in": "path",
                        "description": "Identifiant unique du bâtiment dans le RNB (ID-RNB)",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "PG46YY6YWCX8",
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "comment": {
                                        "type": "string",
                                        "description": "Texte associé à la modification et la justifiant.",
                                        "exemple": "Ce n'est pas un bâtiment mais un arbre.",
                                    },
                                    "is_active": {
                                        "type": "boolean",
                                        "description": LiteralStr(
                                            """\
* `False` : l' ID-RNB est désactivé, car sa présence dans le RNB est une erreur. Ne permet *pas* de signaler une démolition, qui doit se faire par une mise à jour du statut.
* `True` : l'ID-RNB est réactivé. À utiliser uniquement pour annuler une désactivation accidentelle."""
                                        ),
                                    },
                                    "status": {
                                        "type": "string",
                                        "enum": get_status_list(),
                                        "description": f"Statut du bâtiment.",
                                        "exemple": "demolished",
                                    },
                                    "addresses_cle_interop": {
                                        "type": "array",
                                        # currently a bug in gitbook, addding info on items hides the description
                                        # "items": {"type": "string"},
                                        "description": LiteralStr(
                                            """\
Liste des clés d'interopérabilité BAN liées au bâtiment.

Si ce paramêtre est :
* absent, alors les clés ne sont pas modifiées.
* présent et que sa valeur est une liste vide, alors le bâtiment ne sera plus lié à aucune adresse."""
                                        ),
                                        "exemple": [
                                            "75105_8884_00004",
                                            "75105_8884_00006",
                                        ],
                                    },
                                    "shape": {
                                        "type": "string",
                                        "description": """Géométrie du bâtiment au format WKT ou HEX, en WGS84. La géometrie attendue est idéalement un polygone représentant le bâtiment, mais il est également possible de ne donner qu'un point.""",
                                    },
                                },
                                "required": [],
                            }
                        }
                    },
                },
                "responses": {
                    "204": {
                        "description": "Pas de contenu attendu dans la réponse en cas de succès",
                    },
                    "400": {
                        "description": "Requête invalide (données mal formatées ou incomplètes)."
                    },
                    "403": {
                        "description": "L'utilisateur n'a pas les droits nécessaires pour créer un bâtiment."
                    },
                    "503": {"description": "Service temporairement indisponible"},
                    "404": {
                        "description": "ID-RNB inconnu ou une clé d'interopérabilité n'a pas été trouvée auprès de la BAN"
                    },
                },
            }
        }
    )
    def patch(self, request, rnb_id):
        serializer = BuildingUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.data
        user = request.user
        building = get_object_or_404(Building, rnb_id=rnb_id)

        with transaction.atomic():
            contribution = Contribution(
                rnb_id=rnb_id,
                text=data.get("comment"),
                status="fixed",
                status_changed_at=datetime.now(),
                review_user=user,
                report=False,
            )
            contribution.save()

            event_origin = {
                "source": "contribution",
                "contribution_id": contribution.id,
            }

            if data.get("is_active") == False:
                # a building that is not a building has its RNB ID deactivated from the base
                building.deactivate(user, event_origin)
            elif data.get("is_active") == True:
                # a building is reactivated, after a deactivation that should not have
                building.reactivate(user, event_origin)
            else:
                status = data.get("status")
                addresses_cle_interop = data.get("addresses_cle_interop")
                shape = GEOSGeometry(data.get("shape")) if data.get("shape") else None

                try:
                    building.update(
                        user,
                        event_origin,
                        status,
                        addresses_cle_interop,
                        shape=shape,
                    )
                except BANAPIDown:
                    raise ServiceUnavailable(detail="BAN API is currently down")
                except BANUnknownCleInterop:
                    raise NotFound(
                        detail="Cle d'intéropérabilité not found on the BAN API"
                    )
                except BANBadResultType:
                    raise BadRequest(
                        detail="BAN result has not the expected type (must be 'numero')"
                    )
                except OperationOnInactiveBuilding:
                    raise BadRequest(detail="Cannot update inactive buildings")
                except InvalidWGS84Geometry:
                    raise BadRequest(
                        detail="Provided shape is invalid (bad topology or wrong CRS)"
                    )
                except BuildingTooLarge:
                    raise BadRequest(
                        detail="Building area too large. Maximum allowed: 500000m²"
                    )

        # request is successful, no content to send back
        return Response(status=http_status.HTTP_204_NO_CONTENT)
