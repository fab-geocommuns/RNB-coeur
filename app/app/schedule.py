from celery.schedules import crontab

common_schedule = {
    "compute_kpis": {
        "task": "batid.tasks.renew_kpis",
        # everyday at 3am
        "schedule": crontab(hour=3, minute=0),
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

staging_and_sandbox_schedule = {
    **common_schedule,
}

production_schedule = {
    **common_schedule,
    "backup_to_s3": {
        "task": "batid.tasks.backup_to_s3",
        # saturday at 7am
        "schedule": crontab(hour=7, minute=0, day_of_week=6),
    },
    "import_bdtopo": {
        "task": "batid.tasks.queue_full_bdtopo_import",
        # 15 april, 15 july, 15 october, 15 january
        "schedule": crontab(
            minute=0, hour=0, day_of_month=15, month_of_year="1,4,7,10"
        ),
    },
    "import_plots": {
        "task": "batid.tasks.queue_full_plots_import",
        # january 31, april 30, july 31, november 30,
        "schedule": crontab(
            minute=0, hour=0, day_of_month=30, month_of_year="1,4,7,11"
        ),
    },
    "publish_data_gouv": {
        "task": "batid.tasks.publish_datagouv_all",
        # once a week, saturday at 3am
        "schedule": crontab(hour=3, minute=0, day_of_week=6),
    },
    "import_ban": {
        "task": "batid.tasks.queue_full_ban_import",
        "schedule": crontab(minute=0, hour=0, day_of_month="1,15"),
    },
    "create_bal_links": {
        "task": "batid.tasks.queue_full_bal_rnb_links",
        # we create links after the BAN has been imported
        "schedule": crontab(minute=0, hour=0, day_of_month="2,16"),
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
