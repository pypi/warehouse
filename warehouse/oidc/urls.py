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
from __future__ import annotations

import rfc3986


def verify_url_from_reference(*, reference_url: str, url: str) -> bool:
    """
    Verify a given URL against a reference URL.

    This method checks that both URLs have:
        - the same scheme
        - the same authority

    Finally, that the URL is a sub-path of the reference.
    """
    reference_uri = rfc3986.api.uri_reference(reference_url).normalize()
    user_uri = rfc3986.api.uri_reference(url).normalize()

    # Fail fast if the URLs' schemes and authorities don't match.
    if (
        reference_uri.scheme != user_uri.scheme
        or reference_uri.authority != user_uri.authority
    ):
        return False

    # If the URL being verified doesn't have a path but the reference URL
    # does, then it can't possibly be a subpath of the reference URL.
    if not user_uri.path and reference_uri.path:
        return False

    if reference_uri.path:
        # If the reference URL has a path, then the user URL's path should
        # be exactly equivalent or a subpath.
        # The reference URL's path is normalized with a final `/` to ensure
        # that `/foo_bar` isn't treated as a subpath of `/foo`.
        reference_path_prefix = reference_uri.path.rstrip("/") + "/"
        return reference_uri.path == user_uri.path or user_uri.path.startswith(
            reference_path_prefix
        )
    else:
        # If the reference URL has no path, the user URL's path can be anything
        # (since the URL covers the entire domain).
        return True
