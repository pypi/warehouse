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
logger_class = "warehouse.logging.GunicornLogger"

statsd_host = "localhost:8125"

# Disable remote control of the daemon
# On startup, tries to write to `/`, and it does not have permission to,
# raising an exception, but allowing the server to start.
# Instead of overwriting `XDG_RUNTIME_DIR` to a writable target,
# which could affect other code, disable the interface as we are unlikely to need it.
control_socket_disable = True
