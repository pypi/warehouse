release: bin/release
web: bin/start-web python -m gunicorn.app.wsgiapp -c gunicorn-prod.conf.py warehouse.wsgi:application
web-uploads: bin/start-web python -m gunicorn.app.wsgiapp -c gunicorn-uploads.conf.py warehouse.wsgi:application
worker: bin/start-worker celery -A warehouse worker -Q default -l info --max-tasks-per-child 32
worker-malware: bin/start-worker celery -A warehouse worker -Q malware -l info --max-tasks-per-child 32
worker-beat: bin/start-worker celery -A warehouse beat -S redbeat.RedBeatScheduler -l info
# NOTE: --concurrency 1 is CRITICAL for the TUF celery queue,
# since all TUF repository modifications MUST be synchronous.
worker-tuf: bin/start-worker celery -A warehouse worker -Q tuf -l info --max-tasks-per-child 32 --concurrency 1
