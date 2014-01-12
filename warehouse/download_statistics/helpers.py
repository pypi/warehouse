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
import urlparse

from collections import namedtuple
from email.utils import parsedate

from setuptools.package_index import distros_for_url


logger = logging.getLogger(__name__)


ParsedUserAgent = namedtuple("ParsedUserAgent", [
    "raw_user_agent",

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
    ("pypy", "2.2.0"): "2.7.3",
    ("pypy", "2.1.0"): "2.7.3",
}

BANDERSNATCH_RE = re.compile(r"""
\((?P<python_type>.*?)\ (?P<python_version>.*?),
\ (?P<operating_system>.*?)\ (?P<operating_system_version>.*?)\)
""", re.VERBOSE)

DEVPI_RE = re.compile(r"""
\(py(?P<python_version>.*?);\ (?P<operating_system_version>.*?)\)
""", re.VERBOSE)

IGNORED_UAS = re.compile(r"""
(^Go\ .*?\ package\ http) |
(^Wget/) |
(^curl/) |
(^python-requests/) |
(^Homebrew) |
(^Chef\ Client/) |
(^fetch\ libfetch/) |
(^MacPorts) |
(^\(null\)$)
""", re.VERBOSE)

WHEEL_RE = re.compile(r"""
^(?P<namever>(?P<name>.+?)(-(?P<ver>\d.+?))?)
((-(?P<build>\d.*?))?-(?P<pyver>.+?)-(?P<abi>.+?)-(?P<plat>.+?)
\.whl|\.dist-info)$
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
        operating_system, operating_system_version = system_part.split("/", 1)
    elif "setuptools/" in ua or "distribute/" in ua:
        urllib_part, installer_part = ua.split(" ")
        _, python_version = urllib_part.split("/")
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
    elif ua.startswith("devpi-server"):
        devpi_part, rest = ua.split(" ", 1)
        _, installer_version = devpi_part.split("/")
        installer_type = "devpi"
        match = DEVPI_RE.match(rest)
        python_version = match.group("python_version")
        operating_system_version = match.group("operating_system_version")
    elif ua.startswith(("z3c.pypimirror", "pep381client")):
        installer_type, installer_version = ua.split("/")
    elif "Mozilla" in ua or ua.startswith(("BlackBerry", "Opera")):
        installer_type = "browser"
    else:
        if not IGNORED_UAS.search(ua):
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

        raw_user_agent=ua,
    )


def parse_log_line(line):
    # Some weird syslog/fastly thing, just ignore it
    if b"last message repeated" in line:
        return

    row = list(csv.reader([line], delimiter=str(" ")))[0]
    timestamp = row[4]
    req = row[6]
    response_status = row[8]
    ua = row[15]

    try:
        if int(response_status) != 200:
            return
    except ValueError:
        # Broken log lines cause this
        return

    path = urlparse.urlparse(req.split(" ", 1)[1]).path

    if not path.startswith("/packages/"):
        return

    download_time = datetime.datetime(*parsedate(timestamp)[:6])
    directory, filename = posixpath.split(path)

    if not filename or filename.endswith(".asc"):
        return

    project = posixpath.basename(directory)
    return ParsedLogLine(
        package_name=project,
        package_version=compute_version(filename),
        distribution_type=compute_distribution_type(filename),
        download_time=download_time,
        user_agent=parse_useragent(ua)
    )


def compute_version(filename):
    match = WHEEL_RE.match(filename)
    if match:
        return match.group("ver")
    try:
        distro = next(distros_for_url(filename))
    except StopIteration:
        logger.info({
            "event": "download_statitics.compute_version.ignore",
            "filename": filename
        })
        return None
    else:
        return distro.version


def compute_distribution_type(filename):
    if filename.endswith((".tar.gz", ".tar.bz2", ".tgz", ".zip")):
        return "sdist"
    elif filename.endswith(".egg"):
        return "bdist_egg"
    elif filename.endswith(".exe"):
        return "bdist_wininst"
    elif filename.endswith(".whl"):
        return "bdist_wheel"
    elif filename.endswith(".msi"):
        return "bdist_msi"
    elif filename.endswith(".dmg"):
        return "bdist_dmg"
    elif filename.endswith(".rpm"):
        return "bdist_rpm"
    else:
        logger.info(json.dumps({
            "event": "download_statitics.compute_distribution_type.ignore",
            "filename": filename
        }))
        return None
