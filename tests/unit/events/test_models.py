# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.events.models import GeoIPInfo, UserAgentInfo
from warehouse.events.tags import EventTag

from ...common.db.packaging import FileFactory


class TestGeoIPInfo:
    @pytest.mark.parametrize(
        ("test_input", "expected"),
        [
            ({}, ""),
            (
                {"city": "new york", "country_code": "us", "region": "ny"},
                "New York, NY, US",
            ),
            (
                {"city": "new york", "country_code": "us"},
                "New York, US",
            ),
            ({"city": "new york", "region": "ny"}, "New York, NY"),
            ({"region": "ny", "country_code": "us"}, "NY, US"),
            ({"country_name": "United States"}, "United States"),
        ],
    )
    def test_display_output(self, test_input, expected):
        """Create a GeoIPInfo object and test the display method."""
        dataklazz = GeoIPInfo(**test_input)
        assert dataklazz.display() == expected


class TestUserAgentInfo:
    @pytest.mark.parametrize(
        ("test_input", "expected"),
        [
            (
                (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) "
                    "AppleWebKit/601.3.9 (KHTML, like Gecko) Version/9.0.2 "
                    "Safari/601.3.9"
                ),
                {
                    "installer": "Browser",
                    "device": "Mac",
                    "os": "Mac OS X",
                    "user_agent": "Safari",
                },
            ),
            (
                (
                    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:15.0) Gecko/20100101 "
                    "Firefox/15.0.1"
                ),
                {
                    "installer": "Browser",
                    "device": "Other",
                    "os": "Ubuntu",
                    "user_agent": "Firefox",
                },
            ),
            (
                (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 "
                    "Edge/12.246"
                ),
                {
                    "installer": "Browser",
                    "device": "Other",
                    "os": "Windows",
                    "user_agent": "Edge",
                },
            ),
            (
                (
                    "Mozilla/5.0 (X11; CrOS x86_64 8172.45.0) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/51.0.2704.64 Safari/537.36"
                ),
                {
                    "installer": "Browser",
                    "device": "Other",
                    "os": "Chrome OS",
                    "user_agent": "Chrome",
                },
            ),
            (
                (
                    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/47.0.2526.111 Safari/537.36"
                ),
                {
                    "installer": "Browser",
                    "device": "Other",
                    "os": "Windows",
                    "user_agent": "Chrome",
                },
            ),
            (
                (
                    "Mozilla/5.0 (Linux; Android 7.0; Pixel C Build/NRD90M; wv) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
                    "Chrome/52.0.2743.98 Safari/537.36"
                ),
                {
                    "installer": "Browser",
                    "device": "Pixel C",
                    "os": "Android",
                    "user_agent": "Chrome Mobile WebView",
                },
            ),
            (
                (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 12_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/69.0.3497.105 "
                    "Mobile/15E148 Safari/605.1"
                ),
                {
                    "installer": "Browser",
                    "device": "iPhone",
                    "os": "iOS",
                    "user_agent": "Chrome Mobile iOS",
                },
            ),
            (
                (
                    "twine/3.1.1 pkginfo/1.5.0.1 requests/2.22.0 setuptools/45.2.0 "
                    "requests-toolbelt/0.9.1 tqdm/4.42.1 CPython/3.6.9"
                ),
                {"installer": "twine", "implementation": "CPython", "system": None},
            ),
            (
                "twine/4.0.2 CPython/3.11.3",
                {"installer": "twine", "implementation": "CPython", "system": None},
            ),
            (
                "poetry/1.1.11 CPython/3.11.3 Linux/5.15.65+",
                {"implementation": "CPython", "installer": "poetry", "system": "Linux"},
            ),
            (
                "poetry/1.1.13 CPython/3.8.10 Darwin/21.6.0",
                {
                    "implementation": "CPython",
                    "installer": "poetry",
                    "system": "Darwin",
                },
            ),
            (
                "maturin/1.0.0-beta.5",
                {"implementation": None, "installer": "maturin", "system": None},
            ),
            (
                "maturin/0.8.3",
                {"implementation": None, "installer": "maturin", "system": None},
            ),
            (
                "Python-urllib/3.7",
                {"implementation": None, "installer": None, "system": None},
            ),
            (
                "Go-http-client/1.1",
                {"implementation": None, "installer": None, "system": None},
            ),
        ],
    )
    def test_summarizes_user_agents(self, db_request, test_input, expected):
        db_request.headers["User-Agent"] = test_input
        file = FileFactory.create()
        file.record_event(tag=EventTag.File.FileAdd, request=db_request)
        assert file.events[0].additional.get("user_agent_info") == expected

    def test_bad_parse(self, db_request):
        db_request.headers["User-Agent"] = "nobueno"
        file = FileFactory.create()
        file.record_event(tag=EventTag.File.FileAdd, request=db_request)
        assert file.events[0].additional is None

    @pytest.mark.parametrize(
        ("test_input", "expected"),
        [
            (
                {
                    "installer": "Browser",
                    "device": "Mac",
                    "os": "Mac OS X",
                    "user_agent": "Safari",
                },
                "Safari (Mac OS X on Mac)",
            ),
            (
                {
                    "installer": "Browser",
                    "device": "Other",
                    "os": "Ubuntu",
                    "user_agent": "Firefox",
                },
                "Firefox (Ubuntu)",
            ),
            (
                {
                    "installer": "Browser",
                    "device": "Other",
                    "os": "Windows",
                    "user_agent": "Edge",
                },
                "Edge (Windows)",
            ),
            (
                {
                    "installer": "Browser",
                    "device": "Other",
                    "os": "Chrome OS",
                    "user_agent": "Chrome",
                },
                "Chrome (Chrome OS)",
            ),
            (
                {
                    "installer": "Browser",
                    "device": "Other",
                    "os": "Windows",
                    "user_agent": "Chrome",
                },
                "Chrome (Windows)",
            ),
            (
                {
                    "installer": "Browser",
                    "device": "Pixel C",
                    "os": "Android",
                    "user_agent": "Chrome Mobile WebView",
                },
                "Chrome Mobile WebView (Android on Pixel C)",
            ),
            (
                {
                    "installer": "Browser",
                    "device": "iPhone",
                    "os": "iOS",
                    "user_agent": "Chrome Mobile iOS",
                },
                "Chrome Mobile iOS (iOS on iPhone)",
            ),
            (
                {"installer": "twine", "implementation": "CPython", "system": None},
                "twine (CPython)",
            ),
            (
                {"implementation": "CPython", "installer": "poetry", "system": "Linux"},
                "poetry (CPython on Linux)",
            ),
            (
                {
                    "implementation": "CPython",
                    "installer": "poetry",
                    "system": "Darwin",
                },
                "poetry (CPython on Darwin)",
            ),
            (
                {"implementation": None, "installer": "maturin", "system": None},
                "maturin",
            ),
            (
                {"implementation": None, "installer": None, "system": None},
                "Unknown User-Agent",
            ),
            (
                {"implementation": None, "installer": "magictool", "system": "univac"},
                "magictool (univac)",
            ),
            (
                {
                    "installer": "Browser",
                    "device": "univac",
                    "os": "Other",
                    "user_agent": "MagicBrowse",
                },
                "MagicBrowse (univac)",
            ),
            (
                {
                    "installer": "Browser",
                    "device": "Other",
                    "os": "Other",
                    "user_agent": "Other",
                },
                "Unknown Browser",
            ),
            (
                {
                    "installer": "Browser",
                    "device": "Other",
                    "os": "Other",
                    "user_agent": "MagicBrowse",
                },
                "MagicBrowse",
            ),
        ],
    )
    def test_display_output(self, test_input, expected):
        """Create a UserAgentInfo object and test the display method."""
        dataklazz = UserAgentInfo(**test_input)
        assert dataklazz.display() == expected

    @pytest.mark.parametrize(
        ("user_agent", "expected"),
        [
            (
                (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 12_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/69.0.3497.105 "
                    "Mobile/15E148 Safari/605.1"
                ),
                "Chrome Mobile iOS (iOS on iPhone)",
            ),
            ("", "No User-Agent"),
        ],
    )
    def test_user_agent_info(self, db_request, user_agent, expected):
        db_request.headers["User-Agent"] = user_agent
        file = FileFactory.create()
        file.record_event(tag=EventTag.File.FileAdd, request=db_request)
        assert file.events[0].user_agent_info == expected
