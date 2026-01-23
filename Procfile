release: bin/release
web: ddtrace-run python granian-prod.py
web-api: ddtrace-run python granian-prod.py
web-uploads: ddtrace-run python granian-uploads.py
worker: celery -A warehouse worker --concurrency=${CELERY_CONCURRENCY:-1} -Q default -l info --max-tasks-per-child 1024
worker-beat: celery -A warehouse beat -S redbeat.RedBeatScheduler -l info
worker-traced: env DD_SERVICE=warehouse-worker ddtrace-run celery -A warehouse worker --concurrency=${CELERY_CONCURRENCY:-1} -Q default -l info --max-tasks-per-child 32
