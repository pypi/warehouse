web: bin/redis-tls bin/fastly-config && bin/redis-tls gunicorn -b 0.0.0.0:$PORT -n warehouse -k gevent --preload warehouse.wsgi
worker: bin/redis-tls celery -A warehouse worker -l info
