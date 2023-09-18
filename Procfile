release: bin/release
web: bin/start-web ddtrace-run python -m gunicorn.app.wsgiapp -c gunicorn-prod.conf.py warehouse.wsgi:application
web-uploads: bin/start-web ddtrace-run python -m gunicorn.app.wsgiapp -c gunicorn-uploads.conf.py warehouse.wsgi:application
worker: env DD_SERVICE=warehouse-worker DD_UNLOAD_MODULES_FROM_SITECUSTOMIZE=1 bin/start-worker ddtrace-run celery -A warehouse worker -Q default -l info --max-tasks-per-child 32
worker-beat: env DD_SERVICE=warehouse-worker DD_UNLOAD_MODULES_FROM_SITECUSTOMIZE=1 bin/start-worker ddtrace-run celery -A warehouse beat -S redbeat.RedBeatScheduler -l info
