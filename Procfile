web bin/start-web python -m twisted web -n -p tcp:port=$PORT --wsgi warehouse.wsgi.application
worker: bin/start-worker celery -A warehouse worker -l info
