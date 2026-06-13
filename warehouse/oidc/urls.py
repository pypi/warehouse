# SPDX-License-Identifier: Apache-2.0

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
    # Browsers treat "\" as "/" in http(s) URLs (per WHATWG); rfc3986 does
    # not. So "..\x/.." can walk past the reference path in a browser while
    # normalizing to a subpath here, which means the URL we verify and the
    # URL the user lands on can diverge. Reject backslashes.
    if "\\" in url:
        return False

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
    # If the reference URL has no path, the user URL's path can be anything
    # (since the URL covers the entire domain).
    return True
