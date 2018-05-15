from celery.schedules import crontab

from warehouse.credits.tasks import get_contributors


def includeme(config):
    # Add a periodic task to get contributors every 24 hours
    if config.get_settings().get("warehouse.github_access_token"):
        config.add_periodic_task(crontab(minute='2', hour='2'),
                                 get_contributors)
