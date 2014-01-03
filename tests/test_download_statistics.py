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

import datetime
from collections import namedtuple

import alchimia

import pretend

import pytest

from sqlalchemy import create_engine
from sqlalchemy.sql import func

from twisted.internet.defer import succeed
from twisted.python.failure import Failure

from warehouse.download_statistics import tables
from warehouse.download_statistics.cli import (
    TwistedCommand, FastlySyslogProtocol, FastlySyslogProtocolFactory,
    process_logs_main
)
from warehouse.download_statistics.helpers import (
    ParsedUserAgent, ParsedLogLine, parse_useragent, parse_log_line,
    compute_version, compute_distribution_type
)
from warehouse.download_statistics.models import DownloadStatisticsModels


FakeDownload = namedtuple("FakeDownload", [
    "package_name",
    "package_version",
    "distribution_type",
    "python_type",
    "python_release",
    "python_version",
    "installer_type",
    "installer_version",
    "operating_system",
    "operating_system_version",
    "download_time",
    "raw_user_agent",
])


class FakeDownloadStatisticsModels(object):
    def __init__(self):
        self.downloads = []

    def create_download(self, package_name, package_version, distribution_type,
                        python_type, python_release, python_version,
                        installer_type, installer_version, operating_system,
                        operating_system_version, download_time,
                        raw_user_agent):
        self.downloads.append(FakeDownload(
            package_name=package_name,
            package_version=package_version,
            distribution_type=distribution_type,
            python_type=python_type,
            python_release=python_release,
            python_version=python_version,
            installer_type=installer_type,
            installer_version=installer_version,
            operating_system=operating_system,
            operating_system_version=operating_system_version,
            download_time=download_time,
            raw_user_agent=raw_user_agent,
        ))


class FakeThreaderedReactor(object):
    def getThreadPool(self):
        return FakeThreadPool()

    def callFromThread(self, f, *args, **kwargs):
        return f(*args, **kwargs)


class FakeThreadPool(object):
    def callInThreadWithCallback(self, cb, f, *args, **kwargs):
        try:
            result = f(*args, **kwargs)
        except Exception as e:
            cb(False, Failure(e))
        else:
            cb(True, result)


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
                raw_user_agent="Python-urllib/2.7 setuptools/2.0",
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
                raw_user_agent="Python-urllib/2.6 distribute/0.6.10",
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
                raw_user_agent="Python-urllib/2.7",
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
                raw_user_agent="pip/1.4.1 CPython/2.7.6 Darwin/12.5.0",
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
                raw_user_agent=(
                    "pip/1.5rc1 PyPy/2.2.1 Linux/2.6.32-042stab061.2"
                ),
            )
        ),
        (
            "pip/1.4.1 CPython/2.7.3 CYGWIN_NT-6.1-WOW64/1.7.25(0.270/5/3)",
            ParsedUserAgent(
                python_version="2.7.3",
                python_release=None,
                python_type="cpython",

                installer_type="pip",
                installer_version="1.4.1",

                operating_system="CYGWIN_NT-6.1-WOW64",
                operating_system_version="1.7.25(0.270/5/3)",
                raw_user_agent=(
                    "pip/1.4.1 CPython/2.7.3 "
                    "CYGWIN_NT-6.1-WOW64/1.7.25(0.270/5/3)"
                ),
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
                raw_user_agent=(
                    "bandersnatch/1.1 (CPython 2.7.3-final0, "
                    "Linux 3.8.0-31-generic x86_64)"
                ),
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
                raw_user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8)"
            )
        ),
        (
            "BlackBerry9700/5.0.0.743",
            ParsedUserAgent(
                python_version=None,
                python_release=None,
                python_type=None,

                installer_type="browser",
                installer_version=None,

                operating_system=None,
                operating_system_version=None,
                raw_user_agent="BlackBerry9700/5.0.0.743",
            )
        ),
        (
            "z3c.pypimirror/1.0.16",
            ParsedUserAgent(
                python_version=None,
                python_release=None,
                python_type=None,

                installer_type="z3c.pypimirror",
                installer_version="1.0.16",

                operating_system=None,
                operating_system_version=None,
                raw_user_agent="z3c.pypimirror/1.0.16",
            )
        ),
        (
            "pep381client/1.5",
            ParsedUserAgent(
                python_version=None,
                python_release=None,
                python_type=None,

                installer_type="pep381client",
                installer_version="1.5",

                operating_system=None,
                operating_system_version=None,
                raw_user_agent="pep381client/1.5",
            )
        ),
        (
            "Go 1.1 package http",
            ParsedUserAgent(
                python_version=None,
                python_release=None,
                python_type=None,

                installer_type=None,
                installer_version=None,

                operating_system=None,
                operating_system_version=None,
                raw_user_agent="Go 1.1 package http",
            )
        ),
        (
            "errant nonsense here",
            ParsedUserAgent(
                python_version=None,
                python_release=None,
                python_type=None,

                installer_type=None,
                installer_version=None,

                operating_system=None,
                operating_system_version=None,
                raw_user_agent="errant nonsense here",
            )
        )
    ])
    def test_parse_useragent(self, ua, expected):
        assert parse_useragent(ua) == expected

    def test_parse_log_line(self):
        line = (
            '2013-12-08T23:24:40Z cache-c31 pypi-cdn[18322]: 199.182.120.6 '
            '"Sun, 08 Dec 2013 23:24:40 GMT" "-" "GET '
            '/packages/source/I/INITools/INITools-0.2.tar.gz" HTTP/1.1 200 '
            '16930 156751 HIT 326 "(null)" "(null)" "pip/1.5rc1 PyPy/2.2.1 '
            'Linux/2.6.32-042stab061.2"\n'
        )
        assert parse_log_line(line) == ParsedLogLine(
            package_name="INITools",
            package_version="0.2",
            distribution_type="sdist",
            download_time=datetime.datetime(2013, 12, 8, 23, 24, 40),
            user_agent=ParsedUserAgent(
                python_version="2.7.3",
                python_release="2.2.1",
                python_type="pypy",
                installer_type="pip",
                installer_version="1.5rc1",
                operating_system="Linux",
                operating_system_version="2.6.32-042stab061.2",
                raw_user_agent=(
                    "pip/1.5rc1 PyPy/2.2.1 Linux/2.6.32-042stab061.2"
                ),
            )
        )

        line = (
            '2013-12-08T23:27:24Z cache-c31 pypi-cdn[11386]: 199.182.120.6 '
            '"Sun, 08 Dec 2013 23:27:24 GMT" "-" '
            '"GET /packages/2.7/w/wheel/wheel-0.22.0-py2.py3-none-any.whl" '
            'HTTP/1.1 200 54823 329778 HIT 42 "(null)" "(null)" '
            '"pip/1.5rc1 PyPy/2.2.1 Linux/2.6.32-042stab061.2"'
        )
        assert parse_log_line(line) == ParsedLogLine(
            package_name="wheel",
            package_version="0.22.0",
            distribution_type="wheel",
            download_time=datetime.datetime(2013, 12, 8, 23, 27, 24),
            user_agent=ParsedUserAgent(
                python_version="2.7.3",
                python_release="2.2.1",
                python_type="pypy",
                installer_type="pip",
                installer_version="1.5rc1",
                operating_system="Linux",
                operating_system_version="2.6.32-042stab061.2",
                raw_user_agent=(
                    "pip/1.5rc1 PyPy/2.2.1 Linux/2.6.32-042stab061.2"
                ),
            )
        )

    def test_parse_log_line_not_download(self):
        # The URL path doesn't point at a package download
        line = (
            '2013-12-08T23:24:34Z cache-v43 pypi-cdn[18322]: 162.243.117.93 '
            '"Sun, 08 Dec 2013 23:24:33 GMT" "-" "GET /simple/icalendar/3.5" '
            'HTTP/1.1 200 0 0 MISS 0 "(null)" "(null)" "Python-urllib/2.7"'
        )
        assert parse_log_line(line) is None

        line = (
            '2013-12-08T23:24:46Z cache-fra1232 pypi-cdn[7902]: 193.183.99.5 '
            '"Sun, 08 Dec 2013 23:20:28 GMT" "-" "GET '
            '/packages/source/p/pymongo/" HTTP/1.1 200 9944 33573 HIT 1 '
            '"(null)" "en" "Lynx/2.8.8dev.9 libwww-FM/2.14 SSL-MM/1.4.1 '
            'GNUTLS/2.12.14"'
        )
        assert parse_log_line(line) is None

        line = (
            '2013-12-08T23:25:04Z cache-ty68 pypi-cdn[18322]: 1.72.6.148 '
            '"Sun, 08 Dec 2013 23:25:03 GMT" "-" '
            '"GET /packages/source/P/PyMySQL/PyMySQL-0.6.1.tar.gzwget" '
            'HTTP/1.0 301 0 0 MISS 0 "(null)" "(null)" '
            '"Wget/1.12 (solaris2.11)"'
        )
        assert parse_log_line(line) is None

        line = (
            '2013-12-08T23:24:35.150361+00:00 cache-c32 pypi-cdn[11386]: last '
            'message repeated 2 times'
        )
        assert parse_log_line(line) is None

    def test_parse_log_line_non_ascii(self):
        line = (
            b'2013-12-08T23:24:34Z cache-v43 pypi-cdn[18322]: 162.243.117.93 '
            b'"Sun, 08 Dec 2013 23:24:33 GMT" "-" "GET /simple/icalendar/3.5" '
            b'HTTP/1.1 200 0 0 MISS 0 "(null)" "(\xff)" "Python-urllib/2.7"'
        )
        assert parse_log_line(line) is None

    @pytest.mark.parametrize(("filename", "expected"), [
        ("INITools-0.2.tar.gz", "0.2"),
        ("wheel-0.22.0-py2.py3-none-any.whl", "0.22.0"),
        ("Twisted-12.0.0.win32-py2.7.msi", None),
    ])
    def test_compute_version(self, filename, expected):
        assert compute_version(filename) == expected

    @pytest.mark.parametrize(("filename", "expected"), [
        ("foo.tar.gz", "sdist"),
        ("foo.tar.bz2", "sdist"),
        ("foo.tgz", "sdist"),
        ("foo.zip", "sdist"),
        ("foo.tar.gz#md5=blah", "sdist"),
        ("foo.whl", "wheel"),
        ("foo.egg", "egg"),
        ("foo.exe", "exe"),
        ("foo", None)
    ])
    def test_compute_distribution_type(self, filename, expected):
        assert compute_distribution_type(filename) == expected


class TestModels(object):
    def test_create_download(self, _database_url):
        tw_engine = create_engine(
            _database_url,
            strategy=alchimia.TWISTED_STRATEGY,
            reactor=FakeThreaderedReactor()
        )
        models = DownloadStatisticsModels(tw_engine)
        models.create_download(
            package_name="foo",
            package_version="1.0",
            distribution_type="sdist",
            python_type="cpython",
            python_release=None,
            python_version="2.7",
            installer_type="pip",
            installer_version="1.4",
            operating_system=None,
            operating_system_version=None,
            download_time=datetime.datetime.utcnow(),
            raw_user_agent="foo",
        )

        engine = create_engine(_database_url)
        res = engine.execute(func.count(tables.downloads.c.id))
        assert res.scalar() == 1


class TestFastlySyslog(object):
    def test_handle_line(self):
        line = (
            '2013-12-08T23:24:40Z cache-c31 pypi-cdn[18322]: 199.182.120.6 '
            '"Sun, 08 Dec 2013 23:24:40 GMT" "-" "GET '
            '/packages/source/I/INITools/INITools-0.2.tar.gz" HTTP/1.1 200 '
            '16930 156751 HIT 326 "(null)" "(null)" "pip/1.5rc1 PyPy/2.2.1 '
            'Linux/2.6.32-042stab061.2"\n'
        )

        models = FakeDownloadStatisticsModels()
        protocol = FastlySyslogProtocol(models)
        protocol.handle_line(line)

        assert models.downloads == [
            FakeDownload(
                package_name="INITools",
                package_version="0.2",
                distribution_type="sdist",
                download_time=datetime.datetime(2013, 12, 8, 23, 24, 40),
                python_version="2.7.3",
                python_release="2.2.1",
                python_type="pypy",
                installer_type="pip",
                installer_version="1.5rc1",
                operating_system="Linux",
                operating_system_version="2.6.32-042stab061.2",
                raw_user_agent=(
                    "pip/1.5rc1 PyPy/2.2.1 Linux/2.6.32-042stab061.2"
                ),
            )
        ]

    def test_handle_line_not_download(self):
        # The URL path doesn't point at a package download
        line = (
            '2013-12-08T23:24:34Z cache-v43 pypi-cdn[18322]: 162.243.117.93 '
            '"Sun, 08 Dec 2013 23:24:33 GMT" "-" "GET /simple/icalendar/3.5" '
            'HTTP/1.1 301 0 0 MISS 0 "(null)" "(null)" "Python-urllib/2.7"'
        )
        models = FakeDownloadStatisticsModels()
        protocol = FastlySyslogProtocol(models)
        protocol.handle_line(line)

        assert models.downloads == []

    def test_lineReceived_error(self):
        line = (
            '2013-12-08T23:24:40Z cache-c31 pypi-cdn[18322]: 199.182.120.6 '
            '"Sun, 08 Dec 2013 23:24:40 GMT" "-" "GET '
            '/packages/source/I/INITools/INITools-0.2.tar.gz" HTTP/1.1 200 '
            '16930 156751 HIT 326 "(null)" "(null)" "pip/1.5rc1 PyPy/2.2.1 '
            'Linux/2.6.32-042stab061.2"\n'
        )

        models = pretend.stub(create_download=pretend.raiser(ValueError))
        protocol = FastlySyslogProtocol(models)
        protocol.lineReceived(line)
        # No exception was raised

    def test_factory_buildProtocol(self):
        engine = pretend.stub()
        factory = FastlySyslogProtocolFactory(engine)
        protocol = factory.buildProtocol(None)
        assert protocol._models._engine is engine

    def test_main(self, _database_url):
        app = pretend.stub(
            config=pretend.stub(
                database=pretend.stub(
                    download_statistics_url=_database_url
                )
            )
        )
        fake_reactor = pretend.stub()
        process_logs_main(fake_reactor, app)

    def test_twisted_command(self):
        @pretend.call_recorder
        def main(reactor, app):
            return succeed(None)

        app = pretend.stub()
        reactor = pretend.stub(
            addSystemEventTrigger=lambda when, event, f, *args, **kwargs: None,
            run=lambda: None,
        )
        command = TwistedCommand(main, reactor=reactor)
        with pytest.raises(SystemExit) as exc_info:
            command(app)
        assert exc_info.value.code == 0

        assert main.calls == [pretend.call(reactor, app)]
