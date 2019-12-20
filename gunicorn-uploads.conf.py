bind = "unix:/var/run/cabotage/cabotage.sock"
backlog = 512
preload_app = True
max_requests = 32
max_requests_jitter = 8

worker_connections = 256
timeout = 240
keepalive = 2

errorlog = "-"
loglevel = "info"
accesslog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'


def when_ready(server):
    open("/tmp/app-initialized", "w").close()
