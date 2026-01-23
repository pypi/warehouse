# SPDX-License-Identifier: Apache-2.0
"""Granian production configuration for main web traffic."""

from granian import Granian
from granian.constants import Interfaces, HTTPModes
from granian.http import HTTP1Settings
from granian.log import LogLevels


def create_server():
    server = Granian(
        target="warehouse.wsgi:application",
        interface=Interfaces.WSGI,
        uds="/var/run/cabotage/cabotage.sock",
        backlog=2048,
        workers=None,  # Set via CLI or env var
        blocking_threads=1,
        backpressure=1000,  # Similar to worker_connections
        workers_lifetime=3600,  # Worker recycling (1 hour)
        workers_kill_timeout=60,  # Similar to timeout
        respawn_failed_workers=True,
        http=HTTPModes.auto,
        http1_settings=HTTP1Settings(
            keep_alive=True,
        ),
        log_enabled=True,
        log_level=LogLevels.info,
        log_access=True,
        log_access_format='%(addr)s - - [%(time)s] "%(method)s %(path)s %(protocol)s" %(status)d %(dt_ms).3f',
    )

    @server.on_startup
    def when_ready():
        open("/tmp/app-initialized", "w").close()

    return server


if __name__ == "__main__":
    server = create_server()
    server.serve()
