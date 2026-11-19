import logging
import os
import time
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

from api_alpha.utils.sandbox_client import SandboxClient
from batid.services.administrative_areas import dpts_list, slice_dpts
from batid.services.api_request_log import delete_expired_api_request_logs
from batid.services.brevo import RETRYABLE_ERRORS
from batid.services.building import export_city as export_city_job
from batid.services.candidate import Inspector, vacuum_analyze_candidates_if_needed
from batid.services.data_fix.remove_light_buildings import (
    list_light_buildings_france as list_light_buildings_france_job,
)
from batid.services.data_fix.remove_light_buildings import (
    remove_light_buildings as remove_light_buildings_job,
)
from batid.services.data_gouv_publication import (
    DataGouvAccessDenied,
    datagouv_publication_enabled,
    get_area_publish_task,
    publish,
)
from batid.services.imports.import_bal import (
    create_all_bal_links_tasks,
)
from batid.services.imports.import_bal import (
    create_dpt_bal_rnb_links as create_dpt_bal_rnb_links_job,
)
from batid.services.imports.import_ban import (
    create_ban_full_import_tasks,
    import_ban_addresses,
)
from batid.services.imports.import_ban import (
    update_all_cities_ban_ids_reliability as update_all_cities_ban_ids_reliability_job,
)
from batid.services.imports.import_ban import (
    update_dpt_cities_ban_ids_reliability as update_dpt_cities_ban_ids_reliability_job,
)
from batid.services.imports.import_bdnb_2023_01 import (
    import_bdnd_2023_01_addresses,
    import_bdnd_2023_01_bdgs,
)
from batid.services.imports.import_bdtopo import (
    bdtopo_created_candidates,
    bdtopo_dpts_list,
    bdtopo_recente_release_date,
    create_bdtopo_full_import_tasks,
    create_candidate_from_bdtopo,
)
from batid.services.imports.import_cities import import_etalab_cities
from batid.services.imports.import_dgfip_ads import (
    import_dgfip_ads_achievements as import_dgfip_ads_achievements_job,
)
from batid.services.imports.import_dpt import import_etalab_dpts
from batid.services.imports.import_plots import (
    create_plots_full_import_tasks,
    etalab_dpt_list,
    etalab_recent_release_date,
)
from batid.services.imports.import_plots import (
    import_etalab_plots as import_etalab_plots_job,
)
from batid.services.replayable_task import (
    ReplayableTask,
    release_replayable_task_lock,
)
from batid.services.reports.arcep import (
    dl_and_create_arcep_reports,
    reject_irrelevant_arcep_reports,
)
from batid.services.s3_backup.backup_task import backup_to_s3 as backup_to_s3_job
from batid.services.source import (
    Source,
    delete_files_older_than,
    remove_paths_of_successful_task,
)
from batid.services.tchap import Code, TchapLevel, notify_tech, notify_tech_or_log
from batid.utils.auth import make_random_password
from batid.utils.date import iso_to_french_date
from celery import Signature, chain, shared_task
from celery.signals import task_postrun
from django.conf import settings
from django.core.cache import cache


# Sent once the task state is stored, before the ack of acks_late tasks.
@task_postrun.connect
def end_replayable_task(task, state, **_kwargs) -> None:
    if not isinstance(task, ReplayableTask):
        return
    try:
        remove_paths_of_successful_task(request=task.request, state=state)
    finally:
        release_replayable_task_lock(task.request)


@shared_task
def heartbeat() -> None:
    print("Test celery_beat heartbeat")


@shared_task(
    base=ReplayableTask,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def dl_source(src_name: str, src_params: dict):

    src = Source(src_name)
    for param, value in src_params.items():
        src.set_param(param, value)

    logger.info("dl_source: downloading %s", src.url)
    src.download()
    src.uncompress()
    src.remove_archive()
    logger.info("dl_source: download complete for %s %s", src_name, src_params)

    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def import_bdnb_addresses(dpt):
    import_bdnd_2023_01_addresses(dpt)
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def import_bdnb_bdgs(dpt, bulk_launch_uuid=None):
    import_bdnd_2023_01_bdgs(dpt, bulk_launch_uuid)
    return "done"


@shared_task(
    base=ReplayableTask, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3}
)
def convert_bdtopo(src_params, bulk_launch_uuid=None) -> int:
    return create_candidate_from_bdtopo(src_params, bulk_launch_uuid)


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def queue_full_bdtopo_import(
    dpt_start: Optional[str] = None,
    dpt_end: Optional[str] = None,
    released_before: Optional[str] = None,
):

    # Get list of dpts
    dpts = bdtopo_dpts_list(dpt_start, dpt_end)  # type: ignore[arg-type] # type: ignore[arg-type]

    # Default release date to most recent one
    if released_before:
        # date str to date object
        before_date = datetime.strptime(released_before, "%Y-%m-%d").date()
        release_date = bdtopo_recente_release_date(before_date)
    else:
        release_date = bdtopo_recente_release_date()

    notify_tech(
        level=TchapLevel.LAUNCH,
        title="Import BD Topo lancé",
        details=[
            ("Départements", f"{dpts[0]} à {dpts[-1]}"),
            ("Millésime", iso_to_french_date(release_date)),
        ],
    )

    create_bdtopo_full_import_tasks(dpts, release_date).apply_async()

    return f"Queued {len(dpts)} departments import"


@shared_task
def report_bdtopo_import(
    skipped_counts: list[int], *, bulk_launch_uuid: str, release_date: str
) -> None:
    notify_tech_or_log(
        level=TchapLevel.SUCCESS,
        title="Import BD Topo terminé",
        details=[
            ("Millésime", iso_to_french_date(release_date)),
            ("Départements traités", str(len(skipped_counts))),
            ("Candidats créés", str(bdtopo_created_candidates(bulk_launch_uuid))),
            ("Bâtiments sautés", str(sum(skipped_counts))),
            ("À faire", Code("python manage.py inspect_candidates")),
        ],
    )


@shared_task(
    base=ReplayableTask, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3}
)
def import_plots(dpt: str, release_date: str):
    import_etalab_plots_job(dpt, release_date)
    return "done"


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

    notify_tech(
        level=TchapLevel.LAUNCH,
        title="Import du cadastre lancé",
        details=[
            ("Départements", f"{dpts[0]} à {dpts[-1]}"),
            ("Millésime", iso_to_french_date(release_date)),
        ],
    )

    tasks = create_plots_full_import_tasks(dpt_list=dpts, release_date=release_date)
    tasks.append(
        Signature(
            "batid.tasks.notify_import_end",
            kwargs={
                "title": "Import du cadastre terminé",
                "details": [
                    ["Millésime", iso_to_french_date(release_date)],
                    ["Départements", str(len(dpts))],
                ],
            },
            immutable=True,
        )
    )

    chain(*tasks)()
    return f"Queued {len(tasks)} tasks"


@shared_task(
    base=ReplayableTask, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3}
)
def import_cities(dpt):
    import_etalab_cities(dpt)
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def queue_full_cities_import():
    dpts = dpts_list()

    notify_tech(
        level=TchapLevel.LAUNCH,
        title="Import des communes lancé",
        details=[("Départements", f"{dpts[0]} à {dpts[-1]}")],
    )

    tasks = [
        Signature("batid.tasks.import_cities", args=[dpt], immutable=True)
        for dpt in dpts
    ]
    # No vintage: the import reads the current geo.api.gouv.fr cities
    tasks.append(
        Signature(
            "batid.tasks.notify_import_end",
            kwargs={
                "title": "Import des communes terminé",
                "details": [["Départements", str(len(dpts))]],
            },
            immutable=True,
        )
    )

    chain(*tasks)()
    return f"Queued {len(tasks)} tasks"


@shared_task
def notify_import_end(*, title: str, details: list[list[str]]) -> None:
    """Last link of an import chain: runs only when every department succeeded."""
    notify_tech_or_log(
        level=TchapLevel.SUCCESS,
        title=title,
        details=[(label, value) for label, value in details],
    )


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def import_dpts():
    import_etalab_dpts()


@shared_task(
    base=ReplayableTask, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3}
)
def inspect_candidates():
    vacuum_analyze_candidates_if_needed()
    i = Inspector()
    i.inspect()

    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def export_city(insee_code):
    return export_city_job(insee_code)


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def import_dgfip_ads_achievements(filename: str):
    import_dgfip_ads_achievements_job(filename)
    return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 1})
def backup_to_s3():
    # Backing up the database on a separate S3 service
    backup_to_s3_job()
    return "done"


DATAGOUV_RUN_CACHE_TIMEOUT = 3 * 24 * 3600


def _datagouv_run_cache_key(run_id: str) -> str:
    return f"datagouv_published:{run_id}"


def _count_published_area(run_id: str) -> None:
    """Count the published areas of a run in the shared cache: the run (~35 h) outlives
    the Celery results. A lost count under-counts, so the summary alerts."""
    try:
        key = _datagouv_run_cache_key(run_id)
        cache.add(key, 0, timeout=DATAGOUV_RUN_CACHE_TIMEOUT)
        cache.incr(key)
    except Exception:
        logger.exception("data.gouv.fr published areas count failed")


def publish_area_or_report(*, area: str, run_id: str | None = None) -> str:
    """
    Publish one area and never raise, so that a failed area does not stop the
    publish_datagouv_all chain. Exception: a key refused by data.gouv.fr (401/403)
    is raised, since every other area would fail the same way; task_failure then
    alerts once. Other failures go to Sentry (logger.exception) and to the tech
    Tchap room.
    """
    try:
        published = publish(area)
    except DataGouvAccessDenied:
        raise
    except Exception as e:
        logger.exception(f"data.gouv.fr publication failed for area {area}")
        try:
            notify_tech(
                level=TchapLevel.FAILURE,
                title="Échec de la publication data.gouv",
                details=[("Zone", area)],
                error=str(e),
            )
        except Exception:
            # Tchap down must not stop the chain either; Sentry already has the publication error.
            logger.exception("Tchap notification failed")
        return "failed"
    if run_id and published:
        _count_published_area(run_id)
    return "done"


@shared_task
def publish_datagouv_national(*, run_id: str | None = None):
    result = publish_area_or_report(area="nat", run_id=run_id)
    if run_id:
        _notify_datagouv_summary(run_id)
    return result


def _notify_datagouv_summary(run_id: str) -> None:
    total = len(dpts_list()) + 1
    try:
        published = cache.get(_datagouv_run_cache_key(run_id), 0)
    except Exception:
        # The national file is already published: a cache outage must not fail its task
        logger.exception("data.gouv.fr published areas count unreadable")
        published = "inconnu"
    notify_tech_or_log(
        level=TchapLevel.SUCCESS if published == total else TchapLevel.ALERT,
        title="Publication data.gouv terminée",
        details=[("Zones publiées", f"{published} sur {total}")],
    )


@shared_task
def publish_datagouv_dpt(dept: str, *, run_id: str | None = None):
    return publish_area_or_report(area=dept, run_id=run_id)


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 1})
def publish_datagouv_all():
    if not datagouv_publication_enabled():
        value = os.environ.get("ENABLE_DATAGOUV_PUBLICATION")
        notify_tech(
            level=TchapLevel.ALERT,
            title="Publication data.gouv non lancée",
            details=[
                ("Variable", Code("ENABLE_DATAGOUV_PUBLICATION")),
                ("Valeur", Code(value) if value else "non définie"),
            ],
        )
        return "Publication disabled"

    notify_tech(
        level=TchapLevel.LAUNCH,
        title="Publication data.gouv lancée",
        details=[("Zones", "tous les départements et le fichier national")],
    )

    areas = dpts_list() + ["nat"]
    run_id = uuid.uuid4().hex
    tasks = [get_area_publish_task(area, run_id=run_id) for area in areas]

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
def compute_daily_kpis():
    """
    This task is in charge of calculating some KPIs displayed on https://rnb.beta.gouv.fr/stats
    It is too expensive to calculate them on the fly, so we calculate them once a day and store them in a file
    """

    from batid.services.kpi import compute_daily_kpis as compute_daily_kpis_service

    compute_daily_kpis_service()
    return "done"


# @shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
# def delete_to_deactivation(batch_size=10000):
#     delete_to_deactivation_job(batch_size)
#     return "done"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def queue_full_ban_import(
    dpt_start: Optional[str] = None, dpt_end: Optional[str] = None
):

    # Get list of dpts
    dpts = dpts_list(dpt_start, dpt_end)

    notify_tech(
        level=TchapLevel.LAUNCH,
        title="Import des adresses BAN lancé",
        details=[("Départements", f"{dpts[0]} à {dpts[-1]}")],
    )

    tasks = create_ban_full_import_tasks(dpts)

    chain(*tasks)()
    return f"Queued {len(tasks)} tasks"


@shared_task(
    base=ReplayableTask, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3}
)
def import_ban(src_params: dict, bulk_launch_uuid: str = None):  # type: ignore[assignment]
    return import_ban_addresses(src_params, bulk_launch_uuid)


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def update_dpt_cities_ban_ids_reliability(dpt: str):
    return update_dpt_cities_ban_ids_reliability_job(dpt)


# No autoretry: a retry would restart the whole multi-hour run from the first
# department. On failure, resume it with dpt_start.
@shared_task
def update_all_cities_ban_ids_reliability(
    dpt_start: Optional[str] = None, dpt_end: Optional[str] = None
):
    return update_all_cities_ban_ids_reliability_job(dpt_start, dpt_end)


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def queue_full_bal_rnb_links(
    dpt_start: Optional[str] = None, dpt_end: Optional[str] = None
):

    # Get list of dpts
    dpts = dpts_list(dpt_start, dpt_end)

    notify_tech(
        level=TchapLevel.LAUNCH,
        title="Liens bâtiment adresse via les BAL lancés",
        details=[("Départements", f"{dpts[0]} à {dpts[-1]}")],
    )

    all_tasks = create_all_bal_links_tasks(dpts)

    for one_dpt_tasks in all_tasks:
        chain(*one_dpt_tasks)()
    return f"Queued BAL tasks"


@shared_task(
    base=ReplayableTask, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3}
)
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


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 0})
def manual_raise():
    raise Exception("Manual raise for testing purposes")


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def create_arcep_reports() -> uuid.UUID:
    return dl_and_create_arcep_reports()


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def send_monthly_leaderboard_emails():
    from batid.services.leaderboard import (
        send_monthly_leaderboard_emails as send_emails,
    )

    result = send_emails()
    try:
        notify_tech(
            level=TchapLevel.SUCCESS,
            title="Mail mensuel du classement",
            details=[("Bilan", result)],
        )
    except Exception:
        # A retry would send all the emails again
        logger.exception("Tchap report of the leaderboard emails failed")
    return result


@shared_task
def close_irrelevant_reports():
    reject_irrelevant_arcep_reports()


# Other failures are reported by Sentry (Celery integration).
@shared_task(
    name="batid.tasks.send_report_activity_notification",
    autoretry_for=RETRYABLE_ERRORS,
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_report_activity_notification(
    *, report_id: int, action: str, actor_user_id: int, message_id: int
):
    from batid.services.reports.notifications import notify_report_author

    notify_report_author(
        report_id=report_id,
        action=action,
        actor_user_id=actor_user_id,
        message_id=message_id,
    )


@shared_task(
    name="batid.tasks.send_mfa_change_notification",
    autoretry_for=RETRYABLE_ERRORS,
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_mfa_change_notification(*, user_id: int, change: str, changed_at: str):
    from batid.services.mfa import MFAChange, notify_mfa_change

    notify_mfa_change(
        user_id=user_id,
        change=MFAChange(change),
        changed_at=datetime.fromisoformat(changed_at),
    )


@shared_task(
    base=ReplayableTask, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3}
)
def flag_addresses_from_ban(src_params: dict, bulk_launch_uuid: str = None):  # type: ignore[assignment]
    from batid.services.imports.update_addresses_ban import flag_addresses_from_ban_file

    return flag_addresses_from_ban_file(src_params)


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def queue_ban_address_flag_exists(
    dpt_start: Optional[str] = None,
    dpt_end: Optional[str] = None,
):
    """Queue address flag verification tasks for all departments."""
    dpts = dpts_list(dpt_start, dpt_end)
    bulk_launch_uuid = str(uuid.uuid4())

    for dpt in dpts:
        src_params = {"dpt": dpt}
        tasks = [
            Signature(
                "batid.tasks.dl_source",
                args=("ban_with_ids", src_params),
                immutable=True,
            ),
            Signature(
                "batid.tasks.flag_addresses_from_ban",
                args=(src_params, bulk_launch_uuid),
                immutable=True,
            ),
        ]
        chain(*tasks)()

    return f"Queued {len(dpts)} departments"


@shared_task(
    base=ReplayableTask, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3}
)
def compare_addresses_with_ban(src_params: dict, batch_size: int = 1000):  # type: ignore[assignment]
    from batid.services.imports.update_addresses_ban import (
        compare_addresses_with_ban_file,
    )

    return compare_addresses_with_ban_file(src_params, batch_size=batch_size)


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def queue_ban_address_comparison(
    dpt_start: Optional[str] = None,
    dpt_end: Optional[str] = None,
    batch_size: int = 1000,
):
    """Queue the comparison of the existing addresses with the BAN file for all
    departments."""
    dpts = dpts_list(dpt_start, dpt_end)

    for dpt in dpts:
        src_params = {"dpt": dpt}
        tasks = [
            Signature(
                "batid.tasks.dl_source",
                args=("ban_with_ids", src_params),
                immutable=True,
            ),
            Signature(
                "batid.tasks.compare_addresses_with_ban",
                args=(src_params, batch_size),
                immutable=True,
                priority=8,
            ),
        ]
        chain(*tasks)()

    return f"Queued comparison with the BAN file for {len(dpts)} departments"


@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def delete_unlinked_obsolete_addresses_task(batch_size: int = 1000):
    from batid.services.imports.update_addresses_ban import (
        delete_unlinked_obsolete_addresses,
    )

    return delete_unlinked_obsolete_addresses(batch_size)


@shared_task(
    base=ReplayableTask, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3}
)
def geocode_obsolete_addresses_task(batch_size: int = 1000):
    from batid.services.imports.update_addresses_ban import geocode_obsolete_addresses

    return geocode_obsolete_addresses(batch_size)


@shared_task(
    base=ReplayableTask, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3}
)
def update_addresses_from_ban_comparison_task(batch_size: int = 1000):
    from batid.services.imports.update_addresses_ban import (
        update_addresses_from_ban_comparison,
    )

    return update_addresses_from_ban_comparison(batch_size)


@shared_task(
    base=ReplayableTask, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3}
)
def replace_obsolete_addresses_from_geocoding_task(batch_size: int = 1000):
    from batid.services.imports.update_addresses_ban import (
        replace_obsolete_addresses_from_geocoding,
    )

    return replace_obsolete_addresses_from_geocoding(batch_size)


@shared_task
def delete_old_data_files() -> int:
    # Files older than 7 days are leftovers from failed or abandoned runs.
    cutoff = time.time() - 7 * 24 * 3600
    return delete_files_older_than(root_dir=settings.WRITABLE_DATA_DIR, cutoff=cutoff)


@shared_task
def purge_old_api_request_logs() -> int:
    # Safe to rerun; a failed night is caught up by the next one.
    return delete_expired_api_request_logs()
