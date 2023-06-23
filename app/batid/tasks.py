from celery import shared_task
from app.celery import app
from batid.services.imports.import_dpt import import_etalab_dpts
from batid.services.source import Source
from batid.services.imports.import_bdnb7 import import_bdnb7 as import_bdnb7_job
from batid.services.imports.import_bdtopo import import_bdtopo as import_bdtopo_job
from batid.services.imports.import_cities import import_etalab_cities
from batid.services.candidate import Inspector
from batid.services.building import remove_dpt_bdgs as remove_dpt_bdgs_job
from batid.services.building import remove_light_bdgs as remove_light_bdgs_job
from batid.services.building import export_city as export_city_job
from batid.services.building import add_default_status as add_default_status_job
from batid.models import AsyncSignal
from batid.services.signal import AsyncSignalDispatcher
from batid.services.imports.import_dgfip_ads import (
    import_dgfip_ads_achievements as import_dgfip_ads_achievements_job,
)


@shared_task
def test_all() -> str:
    print("test_all")
    return "done"


@shared_task
def dl_source(src, dpt):
    src = Source(src)
    src.set_param("dpt", dpt)

    print(f"-- downloading {src.url}")
    src.download()
    src.uncompress()

    return "done"


@shared_task
def import_bdnb7(dpt):
    import_bdnb7_job(dpt)
    return "done"


@shared_task
def import_bdtopo(dpt):
    import_bdtopo_job(dpt)
    return "done"


@shared_task
def import_cities(dpt):
    import_etalab_cities(dpt)
    return "done"


@shared_task
def import_dpts():
    import_etalab_dpts()


@shared_task
def inspect_candidates():

    while True:
        i = Inspector()
        inspections_len = i.inspect()
        if inspections_len <= 0:
            break

    return "done"


@shared_task
def remove_inspected_candidates():
    i = Inspector()
    i.remove_inspected()
    return "done"


@shared_task
def remove_dpt_bdgs(dpt):
    remove_dpt_bdgs_job(dpt)
    return "done"


@shared_task
def remove_light_bdgs(dpt):
    remove_light_bdgs_job(dpt)
    return "done"


@shared_task
def export_city(insee_code):
    export_city_job(insee_code)
    return "done"


@shared_task
def add_default_status():

    while True:
        c = add_default_status_job()
        if c <= 0:
            break

    return "done"


@shared_task
def import_dgfip_ads_achievements(filename: str):
    import_dgfip_ads_achievements_job(filename)
    return "done"


@shared_task
def dispatch_signal(pk: int):
    s = AsyncSignal.objects.get(pk=pk)
    d = AsyncSignalDispatcher()
    d.dispatch(s)

    return "done"
