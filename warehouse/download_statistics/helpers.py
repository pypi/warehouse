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

import csv
import datetime
import json
import logging
import posixpath
import re
from collections import namedtuple
from email.utils import parsedate

from setuptools.package_index import distros_for_url


logger = logging.getLogger(__name__)


ParsedUserAgent = namedtuple("ParsedUserAgent", [
    "python_type",
    "python_release",
    "python_version",

    "installer_type",
    "installer_version",

    "operating_system",
    "operating_system_version",
])
ParsedLogLine = namedtuple("ParsedLogLine", [
    "package_name",
    "package_version",
    "distribution_type",
    "download_time",
    "user_agent",
])

PYTHON_IMPL_RELEASE_TO_VERSION = {
    ("pypy", "2.2.1"): "2.7.3",
}

BANDERSNATCH_RE = re.compile(r"""
\((?P<python_type>.*?)\ (?P<python_version>.*?),
\ (?P<operating_system>.*?)\ (?P<operating_system_version>.*?)\)
""", re.VERBOSE)


def parse_useragent(ua):
    python_type = None
    python_version = None
    python_release = None
    installer_type = None
    installer_version = None
    operating_system = None
    operating_system_version = None

    if ua.startswith("pip/"):
        pip_part, python_part, system_part = ua.split(" ")
        installer_type, installer_version = pip_part.split("/")
        python_type, python_release = python_part.split("/")
        operating_system, operating_system_version = system_part.split("/")
    elif "setuptools/" in ua or "distribute/" in ua:
        urllib_parse, installer_part = ua.split(" ")
        _, python_version = urllib_parse.split("/")
        installer_type, installer_version = installer_part.split("/")
    elif ua.startswith("Python-urllib"):
        _, python_version = ua.split("/")
        # Probably, technically it could just be a random urllib user
        installer_type = "pip"
    elif ua.startswith("bandersnatch"):
        bander_part, rest = ua.split(" ", 1)
        installer_type, installer_version = bander_part.split("/")
        match = BANDERSNATCH_RE.match(rest)
        python_type = match.group("python_type")
        python_version = match.group("python_version")
        operating_system = match.group("operating_system")
        operating_system_version = match.group("operating_system_version")
    elif "Mozilla" in ua:
        installer_type = "browser"
    else:
        logger.info(json.dumps({
            "event": "download_statitics.parse_useragent.ignore",
            "user_agent": ua,
        }))

    if python_type is not None:
        python_type = python_type.lower()
    if python_type == "cpython" and python_release is not None:
        python_version = python_release
        python_release = None
    if python_version is None:
        python_version = PYTHON_IMPL_RELEASE_TO_VERSION.get(
            (python_type, python_release)
        )

    return ParsedUserAgent(
        python_type=python_type,
        python_release=python_release,
        python_version=python_version,

        installer_type=installer_type,
        installer_version=installer_version,

        operating_system=operating_system,
        operating_system_version=operating_system_version,
    )


def parse_log_line(line):
    row = list(csv.reader([line], delimiter=str(" ")))[0]
    timestamp = row[4]
    req = row[6]
    response_status = row[8]
    ua = row[15]

    if int(response_status) != 200:
        return

    path = req.split(" ", 1)[1]

    if not path.startswith("/packages/"):
        return

    download_time = datetime.datetime(*parsedate(timestamp)[:6])
    directory, filename = posixpath.split(path)
    if not filename:
        return
    project = posixpath.basename(directory)
    return ParsedLogLine(
        package_name=project,
        package_version=next(distros_for_url(filename)).version,
        distribution_type=compute_distribution_type(filename),
        download_time=download_time,
        user_agent=parse_useragent(ua)
    )


def compute_distribution_type(filename):
    if filename.endswith(".tar.gz"):
        return "sdist"
    else:
        logger.info(json.dumps({
            "event": "download_statitics.compute_distribution_type.ignore",
            "filename": filename
        }))
        return None
