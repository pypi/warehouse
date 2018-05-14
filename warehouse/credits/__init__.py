from celery.schedules import crontab

from warehouse.credits.tasks import get_contributors


def includeme(config):
    # Add a periodic task to get contributors every 2 hours, to do this we
    # require the Github access token owned by the pypa warehouse application.
    # if config.get_settings().get("warehouse.github_access_token"):
    #     config.add_periodic_task(crontab(minute=0, hour='*/2'), get_contributors)

    # TEST FIXME
    # for now do every 10 minutes for testing purposes
    # if config.get_settings().get("warehouse.github_access_token"):
    # config.add_periodic_task(crontab(), getcontrib)
    config.add_periodic_task(crontab(minute='*/2'), get_contributors)
    # pass
