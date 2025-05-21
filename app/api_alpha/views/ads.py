class ADSBatchViewSet(RNBLoggingMixin, viewsets.ModelViewSet):
    queryset = ADS.objects.all()
    serializer_class = ADSSerializer
    lookup_field = "file_number"
    pagination_class = PageNumberPagination
    permission_classes = [ADSPermission]
    http_method_names = ["post"]

    max_batch_size = 30

    def create(self, request, *args, **kwargs):
        to_save = []
        errors = {}

        self.validate_length(request.data)

        for ads in request.data:
            try:
                instance = ADS.objects.get(file_number=ads["file_number"])
                serializer = self.get_serializer(instance, data=ads)
            except ADS.DoesNotExist:
                serializer = self.get_serializer(data=ads)

            if serializer.is_valid():
                to_save.append({"serializer": serializer})

            else:
                errors[ads["file_number"]] = serializer.errors

        if len(errors) > 0:
            return Response(errors, status=400)
        else:
            to_show = []
            for item in to_save:
                item["serializer"].save()
                to_show.append(item["serializer"].data)

            return Response(to_show, status=201)

    def validate_length(self, data):
        if len(data) > self.max_batch_size:
            raise ParseError(
                {"errors": f"Too many items in the request. Max: {self.max_batch_size}"}
            )

        if len(data) == 0:
            raise ParseError({"errors": "No data in the request."})


class ADSViewSet(RNBLoggingMixin, viewsets.ModelViewSet):
    queryset = ADS.objects.all()
    serializer_class = ADSSerializer
    lookup_field = "file_number"
    pagination_class = PageNumberPagination
    permission_classes = [ADSPermission]
    http_method_names = ["get", "post", "put", "delete"]

    def get_queryset(self):
        search = ADSSearch(**self.request.query_params.dict())

        if not search.is_valid():
            raise ParseError({"errors": search.errors})

        return search.get_queryset()

    @extend_schema(
        tags=["ADS"],
        operation_id="list_ads",
        summary="Liste et recherche d'ADS",
        description=(
            "Cette API permet de lister et de rechercher des ADS (Autorisation de Droit de Sol). "
            "Les requêtes doivent être authentifiées en utilisant un token. "
            "Les filtres de recherche peuvent être passés en tant que paramètres d'URL."
        ),
        parameters=[
            OpenApiParameter(
                name="q",
                description="Recherche parmi les n° de dossiers (file_number).",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="since",
                description="Récupère tous les dossiers décidés depuis cette date (AAAA-MM-DD).",
                required=False,
                type=str,
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=ADSSerializer,
                examples=[
                    OpenApiExample(
                        name="Exemple",
                        value={
                            "count": 3,
                            "next": None,
                            "previous": None,
                            "results": [
                                {
                                    "file_number": "TEST03818519U9999",
                                    "decided_at": "2023-06-01",
                                    "buildings_operations": [
                                        {
                                            "rnb_id": "A1B2C3A1B2C3",
                                            "shape": None,
                                            "operation": "build",
                                        },
                                        {
                                            "rnb_id": None,
                                            "shape": {
                                                "type": "Point",
                                                "coordinates": [
                                                    5.722961565015281,
                                                    45.1851103238598,
                                                ],
                                            },
                                            "operation": "demolish",
                                        },
                                        {
                                            "rnb_id": "1M2N3O1M2N3O",
                                            "shape": {
                                                "type": "Point",
                                                "coordinates": [
                                                    5.723006573148693,
                                                    45.1851402293713,
                                                ],
                                            },
                                            "operation": "demolish",
                                        },
                                    ],
                                },
                                {
                                    "file_number": "PC3807123200WW",
                                    "decided_at": "2023-05-01",
                                    "buildings_operations": [
                                        {
                                            "rnb_id": "FXFJZNZYGTED",
                                            "shape": None,
                                            "operation": "build",
                                        }
                                    ],
                                },
                                {
                                    "file_number": "PC384712301337",
                                    "decided_at": "2023-02-22",
                                    "buildings_operations": [
                                        {
                                            "rnb_id": "RXNOSN2DUCLG",
                                            "geometry": {
                                                "type": "Point",
                                                "coordinates": [
                                                    5.775791408470412,
                                                    45.256939624268206,
                                                ],
                                            },
                                            "operation": "modify",
                                        }
                                    ],
                                },
                            ],
                        },
                    )
                ],
            )
        },
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        tags=["ADS"],
        operation_id="get_ads",
        summary="Consultation d'une ADS",
        description=(
            "Cette API permet de récupérer une ADS (Autorisation de Droit de Sol). "
            "Les requêtes doivent être authentifiées en utilisant un token. "
        ),
        parameters=[
            OpenApiParameter(
                name="file_number",
                description="Récupération par n° de dossier (file_number).",
                required=True,
                type=str,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=ADSSerializer,
                examples=[
                    OpenApiExample(
                        name="Exemple",
                        value={
                            "file_number": "TEST03818519U9999",
                            "decided_at": "2023-06-01",
                            "buildings_operations": [
                                {
                                    "rnb_id": "A1B2C3A1B2C3",
                                    "shape": None,
                                    "operation": "build",
                                },
                                {
                                    "rnb_id": None,
                                    "shape": {
                                        "type": "Point",
                                        "coordinates": [
                                            5.722961565015281,
                                            45.1851103238598,
                                        ],
                                    },
                                    "operation": "demolish",
                                },
                                {
                                    "rnb_id": "1M2N3O1M2N3O",
                                    "shape": {
                                        "type": "Point",
                                        "coordinates": [
                                            5.723006573148693,
                                            45.1851402293713,
                                        ],
                                    },
                                    "operation": "demolish",
                                },
                            ],
                        },
                    )
                ],
            )
        },
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        tags=["ADS"],
        operation_id="create_ads",
        summary="Création d'une ADS",
        description=(
            "Cet endpoint permet de créer une Autorisation du Droit des Sols (ADS) dans le RNB. "
            "L'API ADS est réservée aux communes et requiert une authentification par token."
        ),
        request=ADSSerializer,
        responses={
            201: OpenApiResponse(
                response=ADSSerializer,
                examples=[
                    OpenApiExample(
                        name="Exemple",
                        value={
                            "file_number": "PCXXXXXXXXXX",
                            "decided_at": "2019-03-18",
                            "buildings_operations": [
                                {
                                    "operation": "demolish",
                                    "rnb_id": "ABCD1234WXYZ",
                                    "shape": None,
                                },
                                {
                                    "operation": "build",
                                    "rnb_id": None,
                                    "shape": {
                                        "type": "Point",
                                        "coordinates": [
                                            2.3552747458487002,
                                            48.86958288638419,
                                        ],
                                    },
                                },
                            ],
                        },
                    )
                ],
            ),
            400: {"description": "Requête invalide"},
        },
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @extend_schema(
        tags=["ADS"],
        operation_id="update_ads",
        summary="Modification d'une ADS",
        description=(
            "Cet endpoint permet de modifier une Autorisation du Droit des Sols (ADS) existante dans le RNB. "
            "L'API ADS est réservée aux communes et requiert une authentification par token."
        ),
        request=ADSSerializer,
        responses={
            200: OpenApiResponse(
                response=ADSSerializer,
                examples=[
                    OpenApiExample(
                        name="Exemple",
                        value={
                            "file_number": "PCXXXXXXXXXX",
                            "decided_at": "2019-03-10",
                            "buildings_operations": [
                                {
                                    "operation": "demolish",
                                    "rnb_id": "7865HG43PLS9",
                                    "shape": None,
                                },
                                {
                                    "operation": "build",
                                    "rnb_id": None,
                                    "shape": {
                                        "type": "Point",
                                        "coordinates": [
                                            2.3552747458487002,
                                            48.86958288638419,
                                        ],
                                    },
                                },
                            ],
                        },
                    )
                ],
            ),
            400: {"description": "Requête invalide"},
            404: {"description": "ADS non trouvée"},
        },
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @extend_schema(
        tags=["ADS"],
        operation_id="delete_ads",
        summary="Suppression d'une ADS",
        description="Cet endpoint permet de supprimer une Autorisation du Droit des Sols (ADS) existante dans le RNB.",
        responses={
            204: {"description": "ADS supprimée avec succès"},
            404: {"description": "ADS non trouvée"},
        },
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


@extend_schema(exclude=True)
class AdsTokenView(APIView):
    permission_classes = [IsSuperUser]

    def post(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                json_users = json.loads(request.body)
                users = []

                for json_user in json_users:
                    password = make_random_password(length=15)
                    user, created = User.objects.get_or_create(
                        username=json_user["username"],
                        defaults={
                            "email": json_user.get("email", None),
                            "password": password,
                        },
                    )

                    group, created = Group.objects.get_or_create(name=ADS_GROUP_NAME)
                    user.groups.add(group)
                    user.save()

                    organization, created = Organization.objects.get_or_create(
                        name=json_user["organization_name"],
                        defaults={
                            "managed_cities": json_user["organization_managed_cities"]
                        },
                    )

                    organization.users.add(user)
                    organization.save()

                    token, created = Token.objects.get_or_create(user=user)

                    users.append(
                        {
                            "username": user.username,
                            "organization_name": json_user["organization_name"],
                            "email": user.email,
                            "password": password,
                            "token": token.key,
                        }
                    )

                return JsonResponse({"created_users": users})
        except json.JSONDecodeError:
            return HttpResponse("Invalid JSON", status=400)
