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

from warehouse.packaging.typosnyper import typo_check_name


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("numpy", None),  # Pass, no typos, exists
        ("NuMpy", None),  # Pass, same as `numpy` after canonicalization
        # repeated characters
        ("nuumpy", "numpy"),
        ("reequests", "requests"),
        # omitted characters
        ("sphnx", "sphinx"),
        ("python-dteutil", "python-dateutil"),
        ("pythondateutil", "python-dateutil"),
        # swapped characters
        ("jinj2a", "jinja2"),
        # swapped words
        ("dateutil-python", "python-dateutil"),
        # common typos
        ("numpi", "numpy"),
        ("requestz", "requests"),
    ],
)
def test_typo_check_name(name, expected, monkeypatch):
    # Set known entries in the _TOP_PROJECT_NAMES list
    # TODO: Replace with a better way to generate corpus
    monkeypatch.setattr(
        "warehouse.packaging.typosnyper._TOP_PROJECT_NAMES",
        {
            "numpy",
            "requests",
            "sphinx",
            "beautifulsoup4",
            "jinja2",
            "python-dateutil",
        },
    )

    assert typo_check_name(name) == expected
