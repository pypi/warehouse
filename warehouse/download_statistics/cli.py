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

import json
import logging

import alchimia

import sqlalchemy

from twisted.internet.defer import Deferred
from twisted.internet.endpoints import StandardIOEndpoint
from twisted.internet.protocol import Factory
from twisted.internet.task import react
from twisted.protocols.basic import LineOnlyReceiver

from warehouse.download_statistics.helpers import parse_log_line
from warehouse.download_statistics.models import DownloadStatisticsModels


logger = logging.getLogger(__name__)


class FastlySyslogProtocol(LineOnlyReceiver):
    delimiter = b"\n"

    def __init__(self, models):
        self._models = models

    def lineReceived(self, line):
        try:
            self.handle_line(line)
        except Exception:
            logger.exception(json.dumps({
                "event": "download_statistics.lineReceived.exception",
                "line": repr(line)
            }))

    def handle_line(self, line):
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
            raw_user_agent=ua.raw_user_agent,
        )


class FastlySyslogProtocolFactory(Factory):
    def __init__(self, engine):
        self._engine = engine

    def buildProtocol(self, addr):
        return FastlySyslogProtocol(
            DownloadStatisticsModels(self._engine)
        )


class TwistedCommand(object):
    def __init__(self, main_func, reactor=None):
        self._main_func = main_func
        self._reactor = reactor

    def __call__(self, app):
        react(self._main_func, [app], _reactor=self._reactor)


def process_logs_main(reactor, app):
    download_statistic_engine = sqlalchemy.create_engine(
        app.config.database.download_statistics_url,
        strategy=alchimia.TWISTED_STRATEGY,
        reactor=reactor
    )
    endpoint = StandardIOEndpoint(reactor)
    endpoint.listen(FastlySyslogProtocolFactory(download_statistic_engine))
    return Deferred()


__commands__ = {
    "process-logs": TwistedCommand(process_logs_main),
}
