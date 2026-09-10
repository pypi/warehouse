# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.oidc.urls import verify_url_from_reference


@pytest.mark.parametrize(
    ("reference", "url", "expected"),
    [
        ("https://example.com", "https://example.com", True),
        ("https://example.com", "https://example.com/", True),
        ("https://example.com", "https://example.com/subpage", True),
        ("https://example.com/", "https://example.com/", True),
        ("https://example.com/", "https://example.com/subpage", True),
        # Mismatch between schemes
        ("https://example.com", "http://example.com", False),
        # Wrong authority
        ("https://example.com", "https://not_example.com", False),
        # Missing sub path
        ("https://example.com/", "https://example.com", False),
        # Not sub path
        ("https://example.com/path1/", "https://example.com/path1/../malicious", False),
        # Backslash bypass: rfc3986 normalizes these as subpaths of the
        # reference, but a browser treats "\" as "/" and walks off-path.
        (
            "https://example.com/path1",
            r"https://example.com/path1/..\x/../malicious/",
            False,
        ),
        (
            "https://github.com/myorg/myproject",
            r"https://github.com/myorg/myproject/..\x/../evil_org/evil_project/",
            False,
        ),
        # Percent-encoded dot bypass: rfc3986 leaves "%2e" literal, but per
        # WHATWG a browser treats ".%2e", "%2e." and "%2e%2e" as double-dot
        # segments and walks off-path.
        (
            "https://example.com/path1",
            "https://example.com/path1/%2e%2e/malicious",
            False,
        ),
        (
            "https://example.com/path1",
            "https://example.com/path1/%2E%2E/malicious",
            False,
        ),
        (
            "https://example.com/path1",
            "https://example.com/path1/.%2e/malicious",
            False,
        ),
        (
            "https://example.com/path1",
            "https://example.com/path1/%2e./malicious",
            False,
        ),
        (
            "https://github.com/myorg/myproject",
            "https://github.com/myorg/myproject/%2e%2e/%2e%2e/evil_org/evil_project",
            False,
        ),
    ],
)
def test_verify_url_from_reference(reference: str, url: str, expected: bool):
    assert verify_url_from_reference(reference_url=reference, url=url) == expected
