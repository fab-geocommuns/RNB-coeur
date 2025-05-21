def get_data_gouv_publication_count():
    # call data.gouv.fr API to get the number of datasets
    req = requests.get("https://www.data.gouv.fr/api/1/datasets/?tag=rnb")
    if req.status_code != 200:
        return None
    else:
        # remove the dataset that is the RNB
        return req.json()["total"] - 1


def get_stats(request):

    api_calls_since_2024_count = APIRequestLog.objects.filter(
        requested_at__gte="2024-01-01T00:00:00Z"
    ).count()
    contributions_count = Contribution.objects.count()
    data_gouv_publication_count = get_data_gouv_publication_count()

    # Get the cached value of the building count
    bdg_count_kpi = get_kpi_most_recent(KPI_ACTIVE_BUILDINGS_COUNT)

    data = {
        "building_counts": bdg_count_kpi.value,
        "api_calls_since_2024_count": api_calls_since_2024_count,
        "contributions_count": contributions_count,
        "data_gouv_publication_count": data_gouv_publication_count,
    }

    renderer = JSONRenderer()
    response = HttpResponse(renderer.render(data), content_type="application/json")

    return response


@extend_schema(exclude=True)
class ContributionsViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = Contribution.objects.all()
    serializer_class = ContributionSerializer

    def create(self, request, *args, **kwargs):
        serializer = ContributionSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        else:
            return Response(serializer.errors, status=400)


def get_contributor_count_and_rank(email):
    rawSql = """
    with ranking as (select email, count(*) as count, rank() over(order by count(*) desc) from batid_contribution where email is not null and email != '' and status != 'refused' group by email order by count desc)
    select count, rank from ranking where email = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(rawSql, [email])
        results = cursor.fetchall()
        target_count, target_rank = results[0]

        return (target_count, target_rank)


def individual_ranking():
    rawSql = """
    select count(*) as count, rank() over(order by count(*) desc)
    from batid_contribution
    where email is not null and email != '' and status != 'refused' and created_at < '2024-09-04'
    group by email
    order by count desc;
    """

    with connection.cursor() as cursor:
        cursor.execute(rawSql)
        results = cursor.fetchall()
        return results


def departement_ranking():
    rawSql = """
    select d.code, d.name, count(*) as count_dpt
    from batid_contribution c
    left join batid_building b on c.rnb_id = b.rnb_id
    left join batid_department_subdivided d on ST_Contains(d.shape, b.point)
    where c.status != 'refused' and c.created_at < '2024-09-04'
    group by d.code, d.name
    order by count_dpt desc, d.code asc;
    """

    with connection.cursor() as cursor:
        cursor.execute(rawSql)
        results = cursor.fetchall()
        return results


def city_ranking():
    rawSql = """
    select city.code_insee, city.name, count(*) as count_city
    from batid_contribution c
    inner join batid_building b on c.rnb_id = b.rnb_id
    inner join batid_city city on ST_Contains(city.shape, b.point)
    where c.status != 'refused' and c.created_at < '2024-09-04'
    group by city.code_insee, city.name
    order by count_city desc, city.code_insee asc;
    """

    with connection.cursor() as cursor:
        cursor.execute(rawSql)
        results = cursor.fetchall()
        return results
