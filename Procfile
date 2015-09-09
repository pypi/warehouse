web: bin/start-stunnel bin/fastly-config && bin/start-stunnel newrelic-admin run-program uwsgi --ini=uwsgi.ini --processes=${WEB_CONCURRENCY:=1}
worker: bin/start-stunnel newrelic-admin run-program celery -A warehouse worker -l info
