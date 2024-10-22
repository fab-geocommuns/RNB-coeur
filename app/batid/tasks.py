from datetime import datetime
from typing import Optional

from celery import chain
from celery import shared_task

from batid.models import AsyncSignal
from batid.services.administrative_areas import dpts_list
from batid.services.building import export_city as export_city_job
from batid.services.building import remove_dpt_bdgs as remove_dpt_bdgs_job
from batid.services.building import remove_light_bdgs as remove_light_bdgs_job
from batid.services.candidate import Inspector
from batid.services.data_fix.remove_light_buildings import (
    list_light_buildings_france as list_light_buildings_france_job,
)
from batid.services.data_fix.remove_light_buildings import (
    remove_light_buildings as remove_light_buildings_job,
)
from batid.services.data_gouv_publication import publish
from batid.services.imports.import_bdnb_2023_01 import import_bdnd_2023_01_addresses
from batid.services.imports.import_bdnb_2023_01 import import_bdnd_2023_01_bdgs
from batid.services.imports.import_bdtopo import bdtopo_recente_release_date
from batid.services.imports.import_bdtopo import create_bdtopo_full_import_tasks
from batid.services.imports.import_bdtopo import create_candidate_from_bdtopo
from batid.services.imports.import_cities import import_etalab_cities
from batid.services.imports.import_dgfip_ads import (
    import_dgfip_ads_achievements as import_dgfip_ads_achievements_job,
)
from batid.services.imports.import_dpt import import_etalab_dpts
from batid.services.imports.import_plots import (
    import_etalab_plots as import_etalab_plots_job,
)
from batid.services.mattermost import notify_if_error
from batid.services.mattermost import notify_tech
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
def dl_source(src_name: str, src_params: dict):

    src = Source(src_name)
    for param, value in src_params.items():
        src.set_param(param, value)

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


@notify_if_error
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def convert_bdtopo(src_params, bulk_launch_uuid=None):

    create_candidate_from_bdtopo(src_params, bulk_launch_uuid)
    return "done"



@notify_if_error
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def queue_full_bdtopo_import(
    dpt_start: Optional[str] = None,
    dpt_end: Optional[str] = None,
    released_before: Optional[str] = None,
):

    notify_tech(
        f"Queuing full BDTopo import tasks.  Dpt start: {dpt_start}, dpt end: {dpt_end}.  Released before: {released_before}"
    )

    # Get list of dpts
    dpts = dpts_list(dpt_start, dpt_end)

    # Default release date to most recent one
    if released_before:
        # date str to date object
        before_date = datetime.strptime(released_before, "%Y-%m-%d").date()
        release_date = bdtopo_recente_release_date(before_date)
    else:
        release_date = bdtopo_recente_release_date()

    tasks = create_bdtopo_full_import_tasks(dpts, release_date)

    chain(*tasks)()
    return f"Queued {len(tasks)} tasks"


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
    publish([dept])
    return "done"


# two tasks to remove light buildings
# first, list the light buildings and save the results in a folder
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 0})
def list_light_buildings_france(start_dpt=None, end_dpt=None):
    list_light_buildings_france_job(start_dpt=start_dpt, end_dpt=end_dpt)
    return "done"


# second, remove the light buildings
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 0})
def remove_light_buildings(folder_name, username, fix_id):
    remove_light_buildings_job(folder_name, username, fix_id)
    return "done"


@notify_if_error
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def renew_stats():

    """
    This task is in charge of calculating some stats displayed on https://rnb.beta.gouv.fr/stats
    It is too expensive to calculate them on the fly, so we calculate them once a day and store them in a file
    :return:
    """

    from batid.services.stats import fetch_stats

    fetch_stats()
    return "done"