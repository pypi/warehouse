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

import pretend
import pytest

from warehouse.packaging.metadata_verification import _verify_url_pypi, verify_url


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
    assert _verify_url_pypi(url, project_name, project_normalized_name) == expected


def test_verify_url():
    # `verify_url` is just a helper function that calls `_verify_url_pypi` and
    # `OIDCPublisher.verify_url`, where the actual verification logic lives.
    publisher_verifies = pretend.stub(verify_url=lambda url: True)
    publisher_fails = pretend.stub(verify_url=lambda url: False)

    assert verify_url(
        url="https://pypi.org/project/myproject/",
        publisher=None,
        project_name="myproject",
        project_normalized_name="myproject",
    )

    assert verify_url(
        url="https://github.com/org/myproject/issues",
        publisher=publisher_verifies,
        project_name="myproject",
        project_normalized_name="myproject",
    )

    assert not verify_url(
        url="example.com",
        publisher=publisher_fails,
        project_name="myproject",
        project_normalized_name="myproject",
    )
