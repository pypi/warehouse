release: bin/release
web: bin/start-web python -m twisted web -n -p tcp:port=$PORT --wsgi warehouse.wsgi.application
web-uploads: bin/start-web python -m twisted web -n -p tcp:port=$PORT --wsgi warehouse.wsgi.application
worker: bin/start-worker celery -A warehouse worker -B -S redbeat.RedBeatScheduler -l info
