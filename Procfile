release: bin/release
web: bin/start-web ddtrace-run python -m gunicorn.app.wsgiapp -c gunicorn-prod.conf.py warehouse.wsgi:application
web-uploads: bin/start-web ddtrace-run python -m gunicorn.app.wsgiapp -c gunicorn-uploads.conf.py warehouse.wsgi:application
worker: DD_SERVICE=warehouse-worker bin/start-worker ddtrace-run celery -A warehouse worker -Q default -l info --max-tasks-per-child 32
worker-beat: bin/start-worker ddtrace-run celery -A warehouse beat -S redbeat.RedBeatScheduler -l info
