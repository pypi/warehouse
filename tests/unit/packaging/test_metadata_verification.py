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

import socket

import pretend
import pytest
import rfc3986
import urllib3

from dns.inet import AF_INET

from warehouse.packaging import metadata_verification as mv

HTML_CONTENT = """
<!DOCTYPE html>
<html class="writer-html5" lang="en" >
<head>
  <meta charset="utf-8" /><meta name="viewport" content="width=device-width" />
{tag_in_head}
  <title>Welcome to the example documentation! &mdash; Example documentation</title>
</head>
<body>
{tag_in_body}
"""


@pytest.mark.parametrize(
    ("url", "project_name", "project_normalized_name", "expected"),
    [
        (  # PyPI /project/ case
            "https://pypi.org/project/myproject",
            "myproject",
            "myproject",
            True,
        ),
        (  # PyPI /p/ case
            "https://pypi.org/p/myproject",
            "myproject",
            "myproject",
            True,
        ),
        (  # pypi.python.org /project/ case
            "https://pypi.python.org/project/myproject",
            "myproject",
            "myproject",
            True,
        ),
        (  # pypi.python.org /p/ case
            "https://pypi.python.org/p/myproject",
            "myproject",
            "myproject",
            True,
        ),
        (  # python.org/pypi/  case
            "https://python.org/pypi/myproject",
            "myproject",
            "myproject",
            True,
        ),
        (  # Normalized name differs from URL
            "https://pypi.org/project/my_project",
            "my_project",
            "my-project",
            True,
        ),
        (  # Normalized name same as URL
            "https://pypi.org/project/my-project",
            "my_project",
            "my-project",
            True,
        ),
        (  # Trailing slash
            "https://pypi.org/project/myproject/",
            "myproject",
            "myproject",
            True,
        ),
        (  # Domains are case insensitive
            "https://PyPI.org/project/myproject",
            "myproject",
            "myproject",
            True,
        ),
        (  # Paths are case-sensitive
            "https://pypi.org/Project/myproject",
            "myproject",
            "myproject",
            False,
        ),
        (  # Wrong domain
            "https://example.com/project/myproject",
            "myproject",
            "myproject",
            False,
        ),
        (  # Wrong path
            "https://pypi.org/something/myproject",
            "myproject",
            "myproject",
            False,
        ),
        (  # Path has extra components
            "https://pypi.org/something/myproject/something",
            "myproject",
            "myproject",
            False,
        ),
        (  # Wrong package name
            "https://pypi.org/project/otherproject",
            "myproject",
            "myproject",
            False,
        ),
        (  # Similar package name
            "https://pypi.org/project/myproject",
            "myproject2",
            "myproject2",
            False,
        ),
        (  # Similar package name
            "https://pypi.org/project/myproject2",
            "myproject",
            "myproject",
            False,
        ),
    ],
)
def test_verify_url_pypi(url, project_name, project_normalized_name, expected):
    assert mv._verify_url_pypi(url, project_name, project_normalized_name) == expected


def test_get_url_content(monkeypatch):
    url = rfc3986.api.uri_reference("https://example.com")

    response = pretend.stub(
        close=pretend.call_recorder(lambda: None),
        read=lambda amt: "content",
    )
    pool = pretend.stub(request=lambda *args, **kwargs: response)
    monkeypatch.setattr(
        urllib3,
        "HTTPSConnectionPool",
        lambda *args, **kwargs: pool,
    )

    assert (
        mv._get_url_content(
            resolved_ip="100.100.100.100", url=url, max_length_bytes=1024
        )
        == "content"
    )
    assert response.close.calls == [pretend.call()]


def test_verify_url_meta_tag_urllib_raises(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args: [(AF_INET, None, None, None, ("1.1.1.1",))],
    )

    def pool_raises(*args, **kwargs):
        raise urllib3.exceptions.ProtocolError()

    monkeypatch.setattr(
        urllib3.HTTPSConnectionPool,
        "__init__",
        pool_raises,
    )

    assert not mv._verify_url_meta_tag("https://example.com", "package1", "package1")


def test_verify_url_meta_tag_getaddrinfo_empty(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args: [],
    )

    assert not mv._verify_url_meta_tag("https://example.com", "package1", "package1")


def test_verify_url_meta_tag_url_validation(monkeypatch):
    valid_content = HTML_CONTENT.format(
        tag_in_head='<meta content="package1" namespace="pypi.org" rel="me" />',
        tag_in_body="",
    )

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args: [(socket.AF_INET, None, None, None, ("1.1.1.1",))],
    )
    monkeypatch.setattr(
        mv,
        "_get_url_content",
        lambda resolved_ip, url, max_length_bytes: valid_content,
    )

    # Valid URLs
    assert mv._verify_url_meta_tag("https://example.com", "package1", "package1")

    # Invalid URLs
    assert not mv._verify_url_meta_tag("invalid url", "package1", "package1")
    assert not mv._verify_url_meta_tag("http://nothttps.com", "package1", "package1")
    assert not mv._verify_url_meta_tag(
        "https://portincluded.com:80", "package1", "package1"
    )
    assert not mv._verify_url_meta_tag(
        "https://portincluded.com:443", "package1", "package1"
    )
    assert not mv._verify_url_meta_tag("missinghttps.com", "package1", "package1")
    # IPs are not allowed
    assert not mv._verify_url_meta_tag("https://1.1.1.1", "package1", "package1")
    assert not mv._verify_url_meta_tag(
        "https://2001:0db8:85a3:0000:0000:8a2e:0370:7334", "package1", "package1"
    )


@pytest.mark.parametrize(
    ("ip_address", "family", "expected"),
    [
        # Domains resolving to global IPs are allowed
        ("1.1.1.1", socket.AF_INET, True),
        ("2607:f8b0:4004:c08::8b", socket.AF_INET6, True),
        # Domains resolving to private and shared IPs should fail
        ("127.0.0.1", socket.AF_INET, False),
        ("0.0.0.0", socket.AF_INET, False),
        ("192.168.2.1", socket.AF_INET, False),
        ("10.0.0.2", socket.AF_INET, False),
        ("172.16.2.3", socket.AF_INET, False),
        ("100.64.100.3", socket.AF_INET, False),
        ("169.254.0.2", socket.AF_INET, False),
        ("::1", socket.AF_INET6, False),
        ("fd12:3456:789a:1::1", socket.AF_INET6, False),
        ("fe80::ab8", socket.AF_INET6, False),
        # Not IPv4 or IPv6
        ("2.0000-0c91-f61f", socket.AF_IPX, False),
        # Invalid IP
        ("100.100.100.100.100", socket.AF_INET, False),
    ],
)
def test_verify_url_meta_tag_ip_validation(monkeypatch, ip_address, family, expected):
    valid_content = HTML_CONTENT.format(
        tag_in_head='<meta content="package1" namespace="pypi.org" rel="me" />',
        tag_in_body="",
    )

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args: [(family, None, None, None, (ip_address,))],
    )
    monkeypatch.setattr(
        mv,
        "_get_url_content",
        lambda resolved_ip, url, max_length_bytes: valid_content,
    )

    assert (
        mv._verify_url_meta_tag("https://example.com", "package1", "package1")
        == expected
    )


@pytest.mark.parametrize(
    ("project_name", "tag_in_head", "tag_in_body", "expected"),
    [
        # Correct HTML, expected package inside content attribute
        (
            "package1",
            '<meta content="package1" namespace="pypi.org" rel="me" />',
            "",
            True,
        ),
        # Correct HTML, expected package inside content attribute with multiple pkgs
        (
            "package1",
            '<meta content="package1 package2 other" namespace="pypi.org" rel="me" />',
            "",
            True,
        ),
        # Correct HTML, meta tag missing
        (
            "package1",
            "",
            "",
            False,
        ),
        # Correct HTML, wrong package inside content attribute
        (
            "package1",
            '<meta content="package2" namespace="pypi.org" rel="me" />',
            "",
            False,
        ),
        # Correct HTML, missing content attribute
        (
            "package1",
            '<meta namespace="pypi.org" rel="me" />',
            "",
            False,
        ),
        # Correct HTML, incorrect namespace attribute
        (
            "package1",
            '<meta content="package1" namespace="notpypi.org" rel="me" />',
            "",
            False,
        ),
        # Correct HTML, missing namespace attribute
        (
            "package1",
            '<meta content="package1" rel="me" />',
            "",
            False,
        ),
        # Correct HTML, incorrect rel attribute
        (
            "package1",
            '<meta content="package1" namespace="pypi.org" rel="notme" />',
            "",
            False,
        ),
        # Correct HTML, missing rel attribute
        (
            "package1",
            '<meta content="package1" namespace="pypi.org" />',
            "",
            False,
        ),
        # Correct HTML, tag inside body instead of head
        (
            "package1",
            "",
            '<meta content="package1" namespace="pypi.org" rel="me" />',
            False,
        ),
    ],
)
def test_verify_url_meta_tag_content_parsing(
    monkeypatch, project_name, tag_in_head, tag_in_body, expected
):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args: [(socket.AF_INET, None, None, None, ("1.1.1.1",))],
    )
    monkeypatch.setattr(
        mv,
        "_get_url_content",
        lambda resolved_ip, url, max_length_bytes: HTML_CONTENT.format(
            tag_in_head=tag_in_head, tag_in_body=tag_in_body
        ),
    )

    assert (
        mv._verify_url_meta_tag(
            url="https://example.com",
            project_name=project_name,
            project_normalized_name=project_name,
        )
        == expected
    )


def test_verify_url_meta_tag_content_parsing_invalid_html(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args: [(socket.AF_INET, None, None, None, ("1.1.1.1",))],
    )
    monkeypatch.setattr(
        mv,
        "_get_url_content",
        lambda resolved_ip, url, max_length_bytes: "<<<<<",
    )
    assert not mv._verify_url_meta_tag("https://example.com", "package1", "package1")


def test_verify_url():
    # `verify_url` is just a helper function that calls `_verify_url_pypi` and
    # `OIDCPublisher.verify_url`, where the actual verification logic lives.
    publisher_verifies = pretend.stub(verify_url=lambda url: True)
    publisher_fails = pretend.stub(verify_url=lambda url: False)

    assert mv.verify_url(
        url="https://pypi.org/project/myproject/",
        publisher=None,
        project_name="myproject",
        project_normalized_name="myproject",
    )

    assert mv.verify_url(
        url="https://github.com/org/myproject/issues",
        publisher=publisher_verifies,
        project_name="myproject",
        project_normalized_name="myproject",
    )

    assert not mv.verify_url(
        url="example.com",
        publisher=publisher_fails,
        project_name="myproject",
        project_normalized_name="myproject",
    )
