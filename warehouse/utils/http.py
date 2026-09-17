# SPDX-License-Identifier: Apache-2.0

import re

from rfc3986 import exceptions, uri_reference, validators
from urllib3.util import parse_url

# WSGI servers reject header values containing control characters. Gunicorn
# validates against ``[ \t\x21-\x7e\x80-\xff]``, so anything in the C0 range
# (plus DEL) makes it raise InvalidHeader from start_response. That escapes as
# an unhandled exception and is answered by gunicorn's own error page, which
# echoes the offending value back, rather than by the response we intend.
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


# FROM https://github.com/django/django/blob/
# 011a54315e46acdf288003566b8570440f5ac985/django/utils/http.py
def is_safe_url(url, host=None):
    """
    Return ``True`` if the url is a safe redirection (i.e. it doesn't point to
    a different host and uses a safe scheme).
    Always returns ``False`` on an empty url.
    """
    if url is not None:
        # Callers hand the URL we approve to webob, which refuses to build a
        # Location header out of a value containing control characters. They
        # also smuggle host changes past the parsing below: urllib.parse drops
        # tab/CR/LF before parsing, so "/\t/evil.com/" looks host-less here,
        # then webob's urljoin collapses it into "//evil.com/".
        if CONTROL_CHARS.search(url):
            return False
        url = url.strip()
    if not url:
        return False
    # Chrome treats \ completely as /
    url = url.replace("\\", "/")
    # Chrome considers any URL with more than two slashes to be absolute, but
    # urlparse is not so flexible. Treat any url with three slashes as unsafe.
    if url.startswith("///"):
        return False
    url_info = parse_url(url)
    # Forbid URLs like http:///example.com - with a scheme, but without a
    # hostname.
    # In that URL, example.com is not the hostname but, a path component.
    # However, Chrome will still consider example.com to be the hostname,
    # so we must not allow this syntax.
    if not url_info.netloc and url_info.scheme:
        return False
    return (not url_info.netloc or url_info.netloc == host) and (
        not url_info.scheme or url_info.scheme in {"http", "https"}
    )


def is_valid_uri(
    uri, require_scheme=True, allowed_schemes=None, require_authority=True
):
    if allowed_schemes is None:
        allowed_schemes = {"http", "https"}
    uri = uri_reference(uri).normalize()
    validator = validators.Validator().allow_schemes(*allowed_schemes)
    if require_scheme:
        validator.require_presence_of("scheme")
    if require_authority:
        validator.require_presence_of("host")

    validator.check_validity_of("scheme", "host", "port", "path", "query")

    try:
        validator.validate(uri)
    except exceptions.ValidationError:
        return False

    return True
