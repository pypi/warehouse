release: bin/release
web: bin/start-web python -m gunicorn.app.wsgiapp -c gunicorn.conf warehouse.wsgi:application
worker: bin/start-worker celery -A warehouse worker -B -S redbeat.RedBeatScheduler -l info
