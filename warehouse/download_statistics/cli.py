# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

import sys

from twisted.internet.defer import Deferred
from twisted.internet.endpoints import StandardIOEndpoint
from twisted.internet.protocol import Factory
from twisted.internet.task import react
from twisted.protocols.basic import LineReceiver

from warehouse.download_statistics.helpers import parse_log_line
from warehouse.download_statistics.models import DownloadStatisticsModels


class FastlySyslogProtocol(LineReceiver):
    def __init__(self, models):
        self._models = models

    def lineReceived(self, line):
        parsed = parse_log_line(line)
        if parsed is None:
            return

        ua = parsed.user_agent
        self._models.create_download(
            package_name=parsed.package_name,
            package_version=parsed.package_version,
            distribution_type=parsed.distribution_type,
            python_type=ua.python_type,
            python_release=ua.python_release,
            python_version=ua.python_version,
            installer_type=ua.installer_type,
            installer_version=ua.installer_version,
            operating_system=ua.operating_system,
            operating_system_version=ua.operating_system_version,
            download_time=parsed.download_time,
        )


class FastlySyslogProtocolFactory(Factory):
    def __init__(self, app):
        self._app = app

    def buildProtocol(self, addr):
        return FastlySyslogProtocol(
            DownloadStatisticsModels(self._app.download_statistics_engine)
        )


class ProcessLogsCommand(object):
    def __call__(self, app):
        react(self.main, [app] + sys.argv)

    def main(self, reactor, app):
        endpoint = StandardIOEndpoint(reactor)
        endpoint.listen(FastlySyslogProtocolFactory(app))
        return Deferred()


__commands__ = {
    "process-logs": ProcessLogsCommand(),
}
