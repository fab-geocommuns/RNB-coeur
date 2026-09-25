from django.forms.models import model_to_dict


def buildings_diff_fields(b1, b2) -> set:
    """
    Compare two building versions (Building, BuildingWithHistory or
    BuildingHistoryOnly) and return the set of fields that differ.
    """
    # field that make an actual difference in the building description
    important_fields = [
        "rnb_id",
        "point",
        "shape",
        "ext_ids",
        "parent_buildings",
        "status",
        "is_active",
        "addresses_internal_id",
        # those 2 fields make no real difference, but they are expected to be equal in our case
        "event_id",
        "event_type",
    ]
    b1 = model_to_dict(b1, fields=important_fields)
    b2 = model_to_dict(b2, fields=important_fields)

    diff = set()
    for key in b1.keys():
        # Two different types means buildings are not identical
        if type(b1[key]) != type(b2[key]):
            diff.add(key)
        # We have a special case for ext_ids which are list of dicts
        elif type(b1[key]) == list and key == "ext_ids":
            # order is not important for the RNB but they still should be sorted to be compared in Python
            sorted1 = sorted(b1[key], key=lambda x: x["id"])
            sorted2 = sorted(b2[key], key=lambda x: x["id"])

            if sorted1 != sorted2:
                diff.add(key)

        elif type(b1[key]) == list:
            if sorted(b1[key]) != sorted(b2[key]):
                diff.add(key)
        elif b1[key] != b2[key]:
            diff.add(key)
    return diff


def building_identicals(b1, b2) -> bool:
    """
    Return True if the two building versions have no difference on the fields
    compared by buildings_diff_fields().
    """
    diff = buildings_diff_fields(b1, b2)
    return len(diff) == 0
