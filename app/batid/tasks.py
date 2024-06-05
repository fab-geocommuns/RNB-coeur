from celery import shared_task

from batid.models import AsyncSignal
from batid.services.building import export_city as export_city_job
from batid.services.building import remove_dpt_bdgs as remove_dpt_bdgs_job
from batid.services.building import remove_light_bdgs as remove_light_bdgs_job
from batid.services.candidate import Inspector
from batid.services.data_gouv_publication import publish
from batid.services.imports.import_bdnb_2023_01 import import_bdnd_2023_01_addresses
from batid.services.imports.import_bdnb_2023_01 import import_bdnd_2023_01_bdgs
from batid.services.imports.import_bdtopo import import_bdtopo as import_bdtopo_job
from batid.services.imports.import_cities import import_etalab_cities
from batid.services.imports.import_dgfip_ads import (
    import_dgfip_ads_achievements as import_dgfip_ads_achievements_job,
)
from batid.services.imports.import_dpt import import_etalab_dpts
from batid.services.imports.import_plots import (
    import_etalab_plots as import_etalab_plots_job,
)
from batid.services.s3_backup.backup_task import backup_to_s3 as backup_to_s3_job
from batid.services.signal import AsyncSignalDispatcher
from batid.services.source import Source


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
def import_bdtopo(dpt, bdtopo_edition="bdtopo_2023_09", bulk_launch_uuid=None):
    import_bdtopo_job(bdtopo_edition, dpt, bulk_launch_uuid)
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
    return export_city_job(insee_code)


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


@shared_task(bind=True, autoretry_for=(Exception,), retry_kwargs={"max_retries": 1})
def backup_to_s3(self):
    # Backing up the database on a separate S3 service
    backup_to_s3_job(task_id=self.request.id)
    return "done"


@shared_task()
def populate_addresses_id_field():
    from batid.services.populate_addresses_id_field import launch_procedure

    launch_procedure()
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 1})
def opendata_publish_national():
    publish(["nat"])
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 1})
def opendata_publish_department(dept):
    publish(dept)
    return "done"
