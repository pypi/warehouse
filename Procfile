release: bin/release
web: ddtrace-run python -m gunicorn.app.wsgiapp -c gunicorn-prod.conf.py warehouse.wsgi:application
web-api: ddtrace-run python -m gunicorn.app.wsgiapp -c gunicorn-prod.conf.py warehouse.wsgi:application
web-uploads: ddtrace-run python -m gunicorn.app.wsgiapp -c gunicorn-uploads.conf.py warehouse.wsgi:application
worker: celery -A warehouse worker --concurrency=${CELERY_CONCURRENCY:-1} -Q default -l info --max-tasks-per-child 1024
worker-beat: celery -A warehouse beat -S redbeat.RedBeatScheduler -l info
worker-traced: env DD_SERVICE=warehouse-worker ddtrace-run celery -A warehouse worker --concurrency=${CELERY_CONCURRENCY:-1} -Q default -l info --max-tasks-per-child 32
