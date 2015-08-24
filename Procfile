web: bin/fastly-config && bin/start-stunnel bin/start-nginx newrelic-admin run-program gunicorn -c conf/gunicorn.conf -b unix:/tmp/nginx.socket --preload warehouse.wsgi
worker: bin/start-stunnel newrelic-admin run-program celery -A warehouse worker -l info
