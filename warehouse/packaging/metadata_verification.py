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

import ipaddress
import socket

import rfc3986
import urllib3

from lxml import etree, html
from rfc3986 import validators as rfc3986_validators
from rfc3986.exceptions import ValidationError as rfc3986ValidationError
from rfc3986.misc import IPv4_MATCHER, IPv6_MATCHER

from warehouse.oidc.models import OIDCPublisher

_pypi_project_urls = [
    "https://pypi.org/project/",
    "https://pypi.org/p/",
    "https://pypi.python.org/project/",
    "https://pypi.python.org/p/",
    "https://python.org/pypi/",
]

_MAX_RESPONSE_LENGTH_BYTES = 100000


class GetContentError(Exception):
    pass


def _verify_url_pypi(url: str, project_name: str, project_normalized_name: str) -> bool:
    """
    Check if a URL matches any of the PyPI URLs for a specific project
    """
    candidate_urls = (
        f"{pypi_project_url}{name}{optional_slash}"
        for pypi_project_url in _pypi_project_urls
        for name in {project_name, project_normalized_name}
        for optional_slash in ["/", ""]
    )

    user_uri = rfc3986.api.uri_reference(url).normalize()
    return any(
        user_uri == rfc3986.api.uri_reference(candidate_url).normalize()
        for candidate_url in candidate_urls
    )


def _get_url_content(
    resolved_ip: str, url: rfc3986.api.URIReference, max_length_bytes: int
) -> bytes:
    """
    Get at least `max_length_bytes` of the contents of a URL

    Raises `GetContentError` on any errors while trying to
    access the URL.
    """
    try:
        http = urllib3.HTTPSConnectionPool(
            host=resolved_ip,
            port=443,
            headers={
                "Host": url.host,
                "User-Agent": "warehouse/1.0 (PyPI URL verifier, https://pypi.org)",
            },
            server_hostname=url.host,
            assert_hostname=url.host,
            retries=False,
            timeout=5,
        )
        r = http.request("GET", url.path if url.path else "/", preload_content=False)
    except Exception:
        raise GetContentError()

    content = next(r.stream(max_length_bytes))

    # When using `preload_content=False`, the HTTP connection must be manually released
    # back to the pool.
    r.drain_conn()
    r.release_conn()

    return content


def _verify_url_meta_tag(
    url: str, project_name: str, project_normalized_name: str
) -> bool:
    user_uri = rfc3986.api.uri_reference(url).normalize()

    # Require the presence of "https" and the host name. Don't allow
    # the presence of ports
    if user_uri.port is not None:
        return False
    validator = (
        rfc3986_validators.Validator()
        .require_presence_of("scheme", "host")
        .allow_schemes("https")
    )

    try:
        validator.validate(user_uri)
    except rfc3986ValidationError:
        return False

    # Only allow registered names for the host (e.g.: google.com, api.github.com),
    # don't allow IP addresses.
    if IPv4_MATCHER.fullmatch(user_uri.host) or IPv6_MATCHER.fullmatch(user_uri.host):
        return False

    # The domain name should not resolve to a private or shared IP address
    try:
        address_tuples = socket.getaddrinfo(user_uri.host, user_uri.port)
        if len(address_tuples) == 0:
            return False
        for family, _, _, _, sockaddr in address_tuples:
            ip_address: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
            if family == socket.AF_INET:
                ip_address = ipaddress.IPv4Address(sockaddr[0])
            elif family == socket.AF_INET6:
                ip_address = ipaddress.IPv6Address(sockaddr[0])
            if ip_address is None or not ip_address.is_global:
                return False
    except (socket.gaierror, ipaddress.AddressValueError):
        return False

    # Use the first IP address returned by `getaddrinfo`
    _, _, _, _, resolved_sockaddr = address_tuples[0]
    resolved_ip = resolved_sockaddr[0]

    try:
        content = _get_url_content(
            resolved_ip=resolved_ip,
            url=user_uri,
            max_length_bytes=_MAX_RESPONSE_LENGTH_BYTES,
        )
    except GetContentError:
        return False

    try:
        html_root = html.document_fromstring(content)
    except (StopIteration, etree.ParserError):
        return False

    meta_tag = html_root.xpath("//head/meta[@namespace='pypi.org' and @rel='me']")

    content = meta_tag[0].get("content") if len(meta_tag) > 0 else None
    if content is None:
        return False

    packages = content.split()
    return project_name in packages or project_normalized_name in packages


def verify_url(
    url: str,
    publisher: OIDCPublisher | None,
    project_name: str,
    project_normalized_name: str,
) -> bool:
    """
    Verify a URL included in a project's metadata

    This function is intended to be used during file uploads, checking the URLs
    included in the metadata against PyPI URLs for that project and against the Trusted
    Publisher used to authenticate the upload (if any).
    """
    if _verify_url_pypi(
        url=url,
        project_name=project_name,
        project_normalized_name=project_normalized_name,
    ):
        return True

    if not publisher:
        return False

    return publisher.verify_url(url)
