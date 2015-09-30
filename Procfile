web: bin/redis-tls bin/fastly-config && bin/redis-tls newrelic-admin run-program uwsgi --ini=uwsgi.ini --processes=${WEB_CONCURRENCY:=1}
worker: bin/redis-tls newrelic-admin run-program celery -A warehouse worker -l info
