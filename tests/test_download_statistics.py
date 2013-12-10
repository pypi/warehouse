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

import pytest

from warehouse.download_statistics import ParsedUserAgent, parse_useragent


class TestParsing(object):
    @pytest.mark.parametrize(("ua", "expected"), [
        (
            "Python-urllib/2.7 setuptools/2.0",
            ParsedUserAgent(
                python_version="2.7",
                python_release=None,
                python_type=None,

                installer_type="setuptools",
                installer_version="2.0",

                operating_system=None,
                operating_system_version=None,
            )
        ),
        (
            "Python-urllib/2.6 distribute/0.6.10",
            ParsedUserAgent(
                python_version="2.6",
                python_release=None,
                python_type=None,

                installer_type="distribute",
                installer_version="0.6.10",

                operating_system=None,
                operating_system_version=None,
            )
        ),
        (
            "Python-urllib/2.7",
            ParsedUserAgent(
                python_version="2.7",
                python_release=None,
                python_type=None,

                installer_type="pip",
                installer_version=None,

                operating_system=None,
                operating_system_version=None,
            )
        ),
        (
            "pip/1.4.1 CPython/2.7.6 Darwin/12.5.0",
            ParsedUserAgent(
                python_version="2.7.6",
                python_release=None,
                python_type="cpython",

                installer_type="pip",
                installer_version="1.4.1",

                operating_system="Darwin",
                operating_system_version="12.5.0",
            )
        ),
        (
            "pip/1.5rc1 PyPy/2.2.1 Linux/2.6.32-042stab061.2",
            ParsedUserAgent(
                python_version="2.7.3",
                python_release="2.2.1",
                python_type="pypy",

                installer_type="pip",
                installer_version="1.5rc1",

                operating_system="Linux",
                operating_system_version="2.6.32-042stab061.2",
            )
        ),
        (
            ("bandersnatch/1.1 (CPython 2.7.3-final0, "
             "Linux 3.8.0-31-generic x86_64)"),
            ParsedUserAgent(
                python_version="2.7.3-final0",
                python_release=None,
                python_type="cpython",

                installer_type="bandersnatch",
                installer_version="1.1",

                operating_system="Linux",
                operating_system_version="3.8.0-31-generic x86_64",
            )
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8)",
            ParsedUserAgent(
                python_version=None,
                python_release=None,
                python_type=None,

                installer_type="browser",
                installer_version=None,

                operating_system=None,
                operating_system_version=None,
            )

        )
    ])
    def test_parse_useragent(self, ua, expected):
        assert parse_useragent(ua) == expected
