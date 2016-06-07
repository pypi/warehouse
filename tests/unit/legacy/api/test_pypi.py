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

from pyramid.httpexceptions import HTTPBadRequest

from warehouse.legacy.api import pypi


def test_exc_with_message():
    exc = pypi._exc_with_message(HTTPBadRequest, "My Test Message.")
    assert isinstance(exc, HTTPBadRequest)
    assert exc.status_code == 400
    assert exc.status == "400 My Test Message."


@pytest.mark.parametrize(
    ("settings", "expected_domain"),
    [
        ({}, "example.com"),
        ({"warehouse.domain": "w.example.com"}, "w.example.com"),
        (
            {
                "forklift.domain": "f.example.com",
                "warehouse.domain": "w.example.com",
            },
            "f.example.com",
        ),
    ],
)
def test_forklifted(settings, expected_domain):
    request = pretend.stub(
        domain="example.com",
        registry=pretend.stub(settings=settings),
    )

    information_url = "TODO"

    resp = pypi.forklifted(request)

    assert resp.status_code == 410
    assert resp.status == (
        "410 This API has moved to https://{}/legacy/. See {} for more "
        "information."
    ).format(expected_domain, information_url)


def test_doap(pyramid_request):
    resp = pypi.doap(pyramid_request)

    assert resp.status_code == 410
    assert resp.status == "410 DOAP is no longer supported."


def test_forbidden_legacy():
    exc, request = pretend.stub(), pretend.stub()
    resp = pypi.forbidden_legacy(exc, request)
    assert resp is exc


def test_doap(pyramid_request):
    resp = pypi.list_classifiers(pyramid_request)

    assert resp.status_code == 200
    # assert resp.status == "410 DOAP is no longer supported."
