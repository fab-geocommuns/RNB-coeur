import uuid
from datetime import datetime
from typing import Optional

from celery import chain
from celery import shared_task

from api_alpha.utils.sandbox_client import SandboxClient
from batid.services.administrative_areas import dpts_list
from batid.services.administrative_areas import slice_dpts
from batid.services.building import export_city as export_city_job
from batid.services.building import remove_dpt_bdgs as remove_dpt_bdgs_job
from batid.services.building import remove_light_bdgs as remove_light_bdgs_job
from batid.services.candidate import Inspector
from batid.services.data_fix.fill_empty_event_origin import (
    fix as fix_fill_empty_event_origin,
)
from batid.services.data_fix.remove_light_buildings import (
    list_light_buildings_france as list_light_buildings_france_job,
)
from batid.services.data_fix.remove_light_buildings import (
    remove_light_buildings as remove_light_buildings_job,
)
from batid.services.data_gouv_publication import get_area_publish_task
from batid.services.data_gouv_publication import publish
from batid.services.imports.import_bal import create_all_bal_links_tasks
from batid.services.imports.import_bal import (
    create_dpt_bal_rnb_links as create_dpt_bal_rnb_links_job,
)
from batid.services.imports.import_ban import create_ban_full_import_tasks
from batid.services.imports.import_ban import import_ban_addresses
from batid.services.imports.import_bdnb_2023_01 import import_bdnd_2023_01_addresses
from batid.services.imports.import_bdnb_2023_01 import import_bdnd_2023_01_bdgs
from batid.services.imports.import_bdtopo import bdtopo_dpts_list
from batid.services.imports.import_bdtopo import bdtopo_recente_release_date
from batid.services.imports.import_bdtopo import create_bdtopo_full_import_tasks
from batid.services.imports.import_bdtopo import create_candidate_from_bdtopo
from batid.services.imports.import_cities import import_etalab_cities
from batid.services.imports.import_dgfip_ads import (
    import_dgfip_ads_achievements as import_dgfip_ads_achievements_job,
)
from batid.services.imports.import_dpt import import_etalab_dpts
from batid.services.imports.import_plots import create_plots_full_import_tasks
from batid.services.imports.import_plots import etalab_dpt_list
from batid.services.imports.import_plots import etalab_recent_release_date
from batid.services.imports.import_plots import (
    import_etalab_plots as import_etalab_plots_job,
)
from batid.services.mattermost import notify_if_error
from batid.services.mattermost import notify_tech
from batid.services.reports.arcep import dl_and_create_arcep_reports
from batid.services.reports.arcep import reject_irrelevant_arcep_reports
from batid.services.s3_backup.backup_task import backup_to_s3 as backup_to_s3_job
from batid.services.source import Source
from batid.utils.auth import make_random_password


@shared_task
def heartbeat() -> None:
    print("Test celery_beat heartbeat")


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

    # Get list of dpts
    dpts = bdtopo_dpts_list(dpt_start, dpt_end)  # type: ignore[arg-type] # type: ignore[arg-type]

    notify_tech(
        f"Queuing full BDTopo import tasks.  Dpt start: {dpts[0]}, dpt end: {dpts[-1]}.  Released before: {released_before}"
    )

    # Default release date to most recent one
    if released_before:
        # date str to date object
        before_date = datetime.strptime(released_before, "%Y-%m-%d").date()
        release_date = bdtopo_recente_release_date(before_date)
    else:
        release_date = bdtopo_recente_release_date()

    all_chains = create_bdtopo_full_import_tasks(dpts, release_date)

    for one_dpt_chain in all_chains:
        one_dpt_chain.apply_async()

    return f"Queued {len(all_chains)} departments import"


@notify_if_error
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def import_plots(dpt: str, release_date: str):
    import_etalab_plots_job(dpt, release_date)
    return "done"


@notify_if_error
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def queue_full_plots_import(
    dpt_start: Optional[str] = None,
    dpt_end: Optional[str] = None,
    released_before: Optional[str] = None,
):

    all_plots_dpts = etalab_dpt_list()
    dpts = slice_dpts(all_plots_dpts, dpt_start, dpt_end)

    # Default release date to most recent one
    if released_before:
        # date str to date object
        before_date = datetime.strptime(released_before, "%Y-%m-%d").date()
        release_date = etalab_recent_release_date(before_date)
    else:
        release_date = etalab_recent_release_date()

    msg = f"Import du cadastre Etalab. Départements: {dpts[0]} à {dpts[-1]}. Date de sortie: {release_date}"
    notify_tech(msg)

    tasks = create_plots_full_import_tasks(dpts, release_date)

    chain(*tasks)()
    return f"Queued {len(tasks)} tasks"


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
def publish_datagouv_national():
    publish("nat")
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 1})
def publish_datagouv_dpt(dept: str):
    publish(dept)
    return "done"


@notify_if_error
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 1})
def publish_datagouv_all():
    notify_tech(
        f"Starting data.gouv.fr publication for all departments and national data."
    )

    areas = dpts_list() + ["nat"]
    tasks = [get_area_publish_task(area) for area in areas]

    chain(*tasks)()

    return f"Queued {len(tasks)} tasks"


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


@shared_task(retry_kwargs={"max_retries": 0})
def deactivate_small_buildings(fix_id: int, batch_size: int = 1000) -> int:
    from batid.services.data_fix.deactivate_small_buildings import (
        deactivate_small_buildings as deactivate_small_buildings_func,
    )

    return deactivate_small_buildings_func(fix_id, batch_size)


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def renew_stats():
    """
    This task is in charge of calculating some stats displayed on https://rnb.beta.gouv.fr/stats
    It is too expensive to calculate them on the fly, so we calculate them once a day and store them in a file
    """

    from batid.services.stats import compute_stats  # type: ignore[import-not-found]

    compute_stats()
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def renew_kpis():
    """
    This task is in charge of calculating some KPIs displayed on https://rnb.beta.gouv.fr/stats
    It is too expensive to calculate them on the fly, so we calculate them once a day and store them in a file
    """

    from batid.services.kpi import compute_today_kpis

    compute_today_kpis()
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 1})
def fill_empty_event_origin(from_rnb_id=None, to_rnb_id=None, batch_size=10000):
    fix_fill_empty_event_origin(from_rnb_id, to_rnb_id, batch_size)
    return "done"


# @shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
# def delete_to_deactivation(batch_size=10000):
#     delete_to_deactivation_job(batch_size)
#     return "done"


@notify_if_error
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def queue_full_ban_import(
    dpt_start: Optional[str] = None, dpt_end: Optional[str] = None
):

    # Get list of dpts
    dpts = dpts_list(dpt_start, dpt_end)

    notify_tech(
        f"Import des adresses BAN. Dpt start. Départements: {dpts[0]} à {dpts[-1]}"
    )

    tasks = create_ban_full_import_tasks(dpts)

    chain(*tasks)()
    return f"Queued {len(tasks)} tasks"


@notify_if_error
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def import_ban(src_params: dict, bulk_launch_uuid: str = None):  # type: ignore[assignment]
    return import_ban_addresses(src_params, bulk_launch_uuid)


@notify_if_error
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def queue_full_bal_rnb_links(
    dpt_start: Optional[str] = None, dpt_end: Optional[str] = None
):

    # Get list of dpts
    dpts = dpts_list(dpt_start, dpt_end)

    notify_tech(
        f"Création de liens bâtiment <> adresse via BAL. Départements: {dpts[0]} à {dpts[-1]}"
    )

    all_tasks = create_all_bal_links_tasks(dpts)

    for one_dpt_tasks in all_tasks:
        chain(*one_dpt_tasks)()
    return f"Queued BAL tasks"


@notify_if_error
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def create_dpt_bal_rnb_links(src_params: dict, bulk_launch_uuid: Optional[str] = None):

    return create_dpt_bal_rnb_links_job(src_params, bulk_launch_uuid)


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def create_sandbox_user(user_data: dict) -> None:
    random_password = make_random_password(length=24)
    SandboxClient().create_user({**user_data, "password": random_password})
    return None


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def fill_empty_event_id(batch_size) -> int:
    from batid.services.data_fix.fill_empty_event_id import fill_empty_event_id

    total = 0

    while True:
        # If no rows are updated, we can stop
        updated_rows = fill_empty_event_id(batch_size=batch_size)
        print(f"Updated {updated_rows} rows")
        total += updated_rows

        print("-------------")
        print(f"Updated {updated_rows} rows")
        print("Total so far: ", total)

        if updated_rows == 0:
            break

    return f"Total updated rows: {total}"  # type: ignore[return-value]


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def fill_empty_event_type(batch_size: int) -> int:
    from batid.services.data_fix.fill_empty_event_type import fill_empty_event_type

    total = 0

    while True:
        # Fill empty event_type in batches of 50_000 rows
        # If no rows are updated, we can stop
        updated_rows = fill_empty_event_type(batch_size=batch_size)
        total += updated_rows

        print("-------------")
        print(f"Updated {updated_rows} rows")
        print("Total so far: ", total)

        if updated_rows == 0:
            break

    return f"Total updated rows: {total}"  # type: ignore[return-value]


@notify_if_error
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 0})
def manual_raise():
    raise Exception("Manual raise for testing purposes")


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def create_arcep_reports() -> uuid.UUID:
    return dl_and_create_arcep_reports()


@shared_task
def close_irrelevant_reports():
    reject_irrelevant_arcep_reports()
