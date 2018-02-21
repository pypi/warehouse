release: bin/release
web: bin/start-web python -m gunicorn.app.wsgiapp --bind 0.0.0.0:$PORT --access-logfile - warehouse.wsgi:application
worker: bin/start-worker celery -A warehouse worker -B -S redbeat.RedBeatScheduler -l info
