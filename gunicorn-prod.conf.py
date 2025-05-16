# SPDX-License-Identifier: Apache-2.0

bind = "unix:/var/run/cabotage/cabotage.sock"
backlog = 2048
preload_app = True
max_requests = 2048
max_requests_jitter = 128

worker_connections = 1000
timeout = 60
keepalive = 2

errorlog = "-"
loglevel = "info"
accesslog = "-"
access_log_format = (
    '%({Warehouse-Hashed-IP}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'
)

statsd_host = "localhost:8125"


def when_ready(server):
    open("/tmp/app-initialized", "w").close()
