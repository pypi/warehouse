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

import unicodedata

from urllib.parse import urlparse

from rfc3986 import uri_reference, validators, exceptions


# FROM https://github.com/django/django/blob/
# 011a54315e46acdf288003566b8570440f5ac985/django/utils/http.py
def is_safe_url(url, host=None):
    """
    Return ``True`` if the url is a safe redirection (i.e. it doesn't point to
    a different host and uses a safe scheme).
    Always returns ``False`` on an empty url.
    """
    if url is not None:
        url = url.strip()
    if not url:
        return False
    # Chrome treats \ completely as /
    url = url.replace("\\", "/")
    # Chrome considers any URL with more than two slashes to be absolute, but
    # urlparse is not so flexible. Treat any url with three slashes as unsafe.
    if url.startswith("///"):
        return False
    url_info = urlparse(url)
    # Forbid URLs like http:///example.com - with a scheme, but without a
    # hostname.
    # In that URL, example.com is not the hostname but, a path component.
    # However, Chrome will still consider example.com to be the hostname,
    # so we must not allow this syntax.
    if not url_info.netloc and url_info.scheme:
        return False
    # Forbid URLs that start with control characters. Some browsers (like
    # Chrome) ignore quite a few control characters at the start of a
    # URL and might consider the URL as scheme relative.
    if unicodedata.category(url[0])[0] == "C":
        return False
    return (not url_info.netloc or url_info.netloc == host) and (
        not url_info.scheme or url_info.scheme in {"http", "https"}
    )


def is_valid_uri(
    uri, require_scheme=True, allowed_schemes={"http", "https"}, require_authority=True
):
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
