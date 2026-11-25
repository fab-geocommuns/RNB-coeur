# Fixtures of the building-direct-write rule, run with:
# semgrep --test --config .semgrep/building-direct-write.yaml .semgrep/building-direct-write.py
from batid.models import Address, Building


def red_bulk_update(buildings_to_update):
    # The shape reviewers flagged in PR #470 and PR #565 (import_bal.py)
    # ruleid: building-direct-write
    Building.objects.bulk_update(buildings_to_update, ["addresses_id"])


def red_queryset_update(rnb_id):
    # ruleid: building-direct-write
    Building.objects.filter(rnb_id=rnb_id).exclude(is_active=False).update(
        status="demolished"
    )


def red_bulk_create(buildings):
    # ruleid: building-direct-write
    Building.objects.bulk_create(buildings)


def red_create(rnb_id):
    # ruleid: building-direct-write
    return Building.objects.create(rnb_id=rnb_id)


def green_business_update(building, user, event_origin):
    # ok: building-direct-write
    building.update(user, event_origin, status="demolished", addresses_cle_interop=None)


def green_business_create(user, event_origin, shape):
    # ok: building-direct-write
    return Building.create_new(user, event_origin, "constructed", [], shape, [])


def green_read(rnb_id):
    # ok: building-direct-write
    return Building.objects.filter(rnb_id=rnb_id).first()


def green_other_model(cle_interop):
    # ok: building-direct-write
    Address.objects.filter(id=cle_interop).update(still_exists=False)
