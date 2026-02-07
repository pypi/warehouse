# SPDX-License-Identifier: Apache-2.0

bind = "unix:/var/run/cabotage/cabotage.sock"
backlog = 512
preload_app = True
max_requests = 32
max_requests_jitter = 8

# Allow large macaroons in Authorization header, default is 8190
limit_request_field_size = 8190 * 4

worker_connections = 256
timeout = 240
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
