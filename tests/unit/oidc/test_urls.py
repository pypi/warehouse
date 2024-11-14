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
    ],
)
def test_verify_url_from_reference(reference: str, url: str, expected: bool):
    assert verify_url_from_reference(reference_url=reference, url=url) == expected
