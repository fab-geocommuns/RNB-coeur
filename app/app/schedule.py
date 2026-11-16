# All times are UTC.
# The weekend is reserved for the data.gouv publication (Saturday 03:00 to
# Sunday ~14:00). Long imports start on a Monday at 00:00 to end before it:
# BD Topo ~64 h, cadastre 8 h (measured in prod, November 2026).

from celery.schedules import crontab

common_schedule = {
    "compute_kpis": {
        "task": "batid.tasks.compute_daily_kpis",
        # everyday at 3am
        "schedule": crontab(hour=3, minute=0),
    },
    "close_irrelevant_reports": {
        "task": "batid.tasks.close_irrelevant_reports",
        # everyday at 4am
        "schedule": crontab(hour=4, minute=0),
    },
}

development_schedule = {
    **common_schedule,
    "heartbeat": {
        "task": "batid.tasks.heartbeat",
        # every 5 minutes
        "schedule": crontab(minute="*/5"),
    },
}

data_cleanup_schedule = {
    "delete_old_data_files": {
        "task": "batid.tasks.delete_old_data_files",
        # sunday at 5am UTC
        "schedule": crontab(hour=5, minute=0, day_of_week=0),
    },
}

staging_and_sandbox_schedule = {
    **common_schedule,
    **data_cleanup_schedule,
}

production_schedule = {
    **common_schedule,
    **data_cleanup_schedule,
    "backup_to_s3": {
        "task": "batid.tasks.backup_to_s3",
        # saturday at 7am
        "schedule": crontab(hour=7, minute=0, day_of_week=6),
    },
    "import_bdtopo": {
        "task": "batid.tasks.queue_full_bdtopo_import",
        # third Monday of January, April, July, October: any day from the 15th
        # to the 21st keeps the vintage chosen by bdtopo_recente_release_date
        "schedule": crontab(
            minute=0,
            hour=0,
            day_of_month="15-21",
            day_of_week=1,
            month_of_year="1,4,7,10",
        ),
    },
    "import_plots": {
        "task": "batid.tasks.queue_full_plots_import",
        # Etalab puts each quarterly release online 4 to 6 weeks after the date
        # in its folder name: the fourth Monday of the following month catches it,
        # one week after the BD Topo import
        "schedule": crontab(
            minute=0,
            hour=0,
            day_of_month="22-28",
            day_of_week=1,
            month_of_year="1,4,7,10",
        ),
    },
    "publish_data_gouv": {
        "task": "batid.tasks.publish_datagouv_all",
        # once a week, saturday at 3am
        "schedule": crontab(hour=3, minute=0, day_of_week=6),
    },
    # Temporary deactivation of those imports during the
    # Great Refresh of the clés d'interop
    # "import_ban": {
    #     "task": "batid.tasks.queue_full_ban_import",
    #     "schedule": crontab(minute=0, hour=0, day_of_month="1,15"),
    # },
    # "create_bal_links": {
    #     "task": "batid.tasks.queue_full_bal_rnb_links",
    #     # we create links after the BAN has been imported
    #     "schedule": crontab(minute=0, hour=0, day_of_month="2,16"),
    # },
    "send_monthly_leaderboard_emails": {
        "task": "batid.tasks.send_monthly_leaderboard_emails",
        # 1st of each month at 6am UTC
        "schedule": crontab(hour=6, minute=0, day_of_month=1),
    },
    "import_cities": {
        "task": "batid.tasks.queue_full_cities_import",
        # Insee publishes the new COG in march
        # twice a year: april 1st and october 1st at 2am
        "schedule": crontab(minute=0, hour=2, day_of_month=1, month_of_year="4,10"),
    },
}


def get_celery_beat_schedule(environment: str) -> dict:
    if environment == "test":
        return {}
    if environment == "production":
        return production_schedule
    if environment == "development":
        return development_schedule
    if environment in ["staging", "sandbox"]:
        return staging_and_sandbox_schedule
    raise ValueError(f"Invalid environment: {environment}")
