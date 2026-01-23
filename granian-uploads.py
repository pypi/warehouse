# SPDX-License-Identifier: Apache-2.0
"""Granian configuration for package upload traffic (longer timeouts)."""

from granian import Granian
from granian.constants import Interfaces, HTTPModes
from granian.http import HTTP1Settings
from granian.log import LogLevels


def create_server():
    server = Granian(
        target="warehouse.wsgi:application",
        interface=Interfaces.WSGI,
        uds="/var/run/cabotage/cabotage.sock",
        backlog=512,
        workers=None,  # Set via CLI or env var
        blocking_threads=1,
        backpressure=256,  # Similar to worker_connections (uploads need fewer)
        workers_lifetime=900,  # More aggressive recycling (15 min) - was max_requests=32
        workers_kill_timeout=240,  # Longer timeout for uploads (4 minutes)
        respawn_failed_workers=True,
        http=HTTPModes.auto,
        http1_settings=HTTP1Settings(
            keep_alive=True,
            max_buffer_size=417792 * 4,  # Larger buffer for macaroon headers
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
