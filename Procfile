release: bin/release
web: bin/start-web ddtrace-run python -m gunicorn.app.wsgiapp -c gunicorn-prod.conf.py warehouse.wsgi:application
web-api: bin/start-web ddtrace-run python -m gunicorn.app.wsgiapp -c gunicorn-prod.conf.py warehouse.wsgi:application
web-uploads: bin/start-web ddtrace-run python -m gunicorn.app.wsgiapp -c gunicorn-uploads.conf.py warehouse.wsgi:application
worker: bin/start-worker celery -A warehouse worker $EXTRA_CELERY_ARGS -Q default -l info --max-tasks-per-child 1024
worker-beat: bin/start-worker celery -A warehouse beat -S redbeat.RedBeatScheduler -l info
worker-traced: env DD_SERVICE=warehouse-worker bin/start-worker ddtrace-run celery -A warehouse worker $EXTRA_CELERY_ARGS -Q default -l info --max-tasks-per-child 32
worker-drain-sqs: env BROKER_URL=sqs:///?region=us-east-2&queue_name_prefix=pypi-worker bin/start-worker $EXTRA_CELERY_ARGS celery -A warehouse worker -Q default -l info --max-tasks-per-child 1024
