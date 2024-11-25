from django.db import connection
from django.db import transaction
from django.forms.models import model_to_dict
from psycopg2.extras import DateTimeTZRange

from batid.models import Building
from batid.models import BuildingHistoryOnly


def fix(batch_size):

    n = 1
    rnb_id_cut = "0"

    while n > 0:
        buildings = Building.objects.raw(
            f"select id, rnb_id from batid_building bb where rnb_id > '{rnb_id_cut}' order by rnb_id limit {batch_size};"
        )
        n = len(buildings)

        if n == 0:
            break
        else:
            rnb_id_cut = buildings[-1].rnb_id
            print(f"cleaning db, currently fixing {rnb_id_cut}")

        with transaction.atomic():
            with connection.cursor() as cursor:
                raw_sql = "ALTER TABLE public.batid_building DISABLE TRIGGER building_versioning_trigger;"
                cursor.execute(raw_sql)

                for building in buildings:
                    rnb_id = building.rnb_id
                    squash_history(rnb_id)
                    fill_events(rnb_id)

                raw_sql = "ALTER TABLE public.batid_building ENABLE TRIGGER building_versioning_trigger;"
                cursor.execute(raw_sql)


def squash_history(rnb_id):
    """
    Some buildings have been updated, but without any actual difference in the data.
    Behavior has been fixed with https://github.com/fab-geocommuns/RNB-coeur/pull/497, but history needs to be fixed as well.
    """

    # fetch all versions of a particular RNB ID, in both building_history and building tables
    building_versions = list(
        BuildingHistoryOnly.objects.all().filter(rnb_id=rnb_id).order_by("sys_period")
    ) + list(Building.objects.all().filter(rnb_id=rnb_id).order_by("sys_period"))

    n = len(building_versions)
    i = 0

    while i < n - 1:
        j = i + 1

        if building_versions[i].event_type is None:
            # we only consider squashing building versions with empty event_type
            while j < n:
                if building_identicals(building_versions[i], building_versions[j]):
                    # we keep looping, to see if next version is also identical
                    j = j + 1
                else:
                    # stop looping, time to squash
                    break

            if j > i + 1:
                # at least 2 identical lines have been detected, let's squash
                squash_building_versions(
                    building_versions, start_index=i, end_index=j - 1
                )

        # continue the loop from there
        i = j


def buildings_diff_fields(b1, b2) -> set:
    # field that make an actual difference in the building description
    important_fields = [
        "rnb_id",
        "point",
        "shape",
        "ext_ids",
        "parent_buildings",
        "status",
        "is_active",
        "addresses_id",
        # those 2 fields make no real difference, but they are expected to be equal in our case
        "event_id",
        "event_type",
    ]
    b1 = model_to_dict(b1, fields=important_fields)
    b2 = model_to_dict(b2, fields=important_fields)

    diff = set()
    for key in b1.keys():
        if type(b1[key]) != type(b2[key]):
            diff.add(key)
        elif type(b1[key]) == dict:
            # order is not important in rnb lists
            # duplicates are not expected
            if set(b1[key]) != set(b2[key]):
                diff.add(key)
        elif type(b1[key]) == list:
            if sorted(b1[key]) != sorted(b2[key]):
                diff.add(key)
        elif b1[key] != b2[key]:
            diff.add(key)
    return diff


def building_identicals(b1, b2) -> bool:
    diff = buildings_diff_fields(b1, b2)
    return len(diff) == 0


def squash_building_versions(building_versions, start_index, end_index):
    # modify the last row because it is possibly the current version of the building
    lower = building_versions[start_index].sys_period.lower
    building = building_versions[end_index]
    building.sys_period = DateTimeTZRange(lower=lower, upper=building.sys_period.upper)
    building.save()

    # delete other rows
    for i in range(start_index, end_index):
        b = building_versions[i]
        b.delete()


def fill_events(rnb_id):
    building_versions = list(
        BuildingHistoryOnly.objects.all().filter(rnb_id=rnb_id).order_by("sys_period")
    ) + list(Building.objects.all().filter(rnb_id=rnb_id).order_by("sys_period"))

    for i, building_version in enumerate(building_versions):
        # we only write event types if it is currently empty
        if building_version.event_type is None:
            if i == 0:
                # first occurence is a creation
                building_version.event_type = "creation"
            else:
                # and then we have updates
                building_version.event_type = "update"
            building_version.save()
