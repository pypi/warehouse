release: bin/release
web: bin/start-web python -m gunicorn.app.wsgiapp -c gunicorn.conf warehouse.wsgi:application
web-uploads: bin/start-web python -m gunicorn.app.wsgiapp -c gunicorn-uploads.conf warehouse.wsgi:application
worker: bin/start-worker celery -A warehouse worker -l info --max-tasks-per-child 32
worker-beat: bin/start-worker celery -A warehouse beat -S redbeat.RedBeatScheduler -l info
