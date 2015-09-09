web: bin/start-stunnel bin/fastly-config && bin/start-stunnel newrelic-admin run-program uwsgi --ini=uwsgi.ini --http-socket=0.0.0.0:$PORT
worker: bin/start-stunnel newrelic-admin run-program celery -A warehouse worker -l info
