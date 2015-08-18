web: bin/fastly-config && bin/start-stunnel python -m warehouse serve -b 0.0.0.0:$PORT
worker: bin/start-stunnel celery -A warehouse worker -l info
