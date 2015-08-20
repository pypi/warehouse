web: bin/fastly-config && bin/start-stunnel newrelic-admin run-program gunicorn -b 0.0.0.0:$PORT warehouse.wsgi
worker: bin/start-stunnel newrelic-admin run-program celery -A warehouse worker -l info
