from celery import shared_task
from app.celery import app
from batid.services.imports.import_dpt import import_etalab_dpts
from batid.services.source import Source

from batid.services.imports.import_bdnb_2023_01 import (
    import_bdnd_2023_01_bdgs,
    import_bdnd_2023_01_addresses,
)

from batid.services.imports.import_bdtopo import import_bdtopo as import_bdtopo_job
from batid.services.imports.import_plots import (
    import_etalab_plots as import_etalab_plots_job,
)
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


@shared_task(
    autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5}
)
def dl_source(src, dpt):
    src = Source(src)
    src.set_param("dpt", dpt)

    print(f"-- downloading {src.url}")
    src.download()
    src.uncompress()
    src.remove_archive()

    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def import_bdnb_addresses(dpt):
    import_bdnd_2023_01_addresses(dpt)
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def import_bdnb_bdgs(dpt, bulk_launch_uuid=None):
    import_bdnd_2023_01_bdgs(dpt, bulk_launch_uuid)
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def import_bdtopo(dpt, bulk_launch_uuid=None):
    import_bdtopo_job(dpt, bulk_launch_uuid)
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def import_plots(dpt):
    import_etalab_plots_job(dpt)
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def import_cities(dpt):
    import_etalab_cities(dpt)
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def import_dpts():
    import_etalab_dpts()


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def inspect_candidates():
    print("---- Inspecting candidates ----")

    i = Inspector()
    i.inspect()

    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def remove_dpt_bdgs(dpt):
    remove_dpt_bdgs_job(dpt)
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def remove_light_bdgs(dpt):
    remove_light_bdgs_job(dpt)
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def export_city(insee_code):
    export_city_job(insee_code)
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def add_default_status():
    print("---- Adding default status ----")

    added = 0
    after_id = 0

    while True:
        count, after_id = add_default_status_job(after_id)
        added += count
        print(f"Added {added} default status so far")
        if count <= 0:
            break

    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def import_dgfip_ads_achievements(filename: str):
    import_dgfip_ads_achievements_job(filename)
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def dispatch_signal(pk: int):
    s = AsyncSignal.objects.get(pk=pk)
    d = AsyncSignalDispatcher()
    d.dispatch(s)

    return "done"
