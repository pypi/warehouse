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
import pymacaroons

from pyramid.httpexceptions import HTTPBadRequest, HTTPMovedPermanently, HTTPNotFound, HTTPUnauthorized

from warehouse.legacy.api import pypi

from ....common.db.classifiers import ClassifierFactory
from ....common.db.accounts import UserFactory
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons import services
from warehouse.macaroons.models import Macaroon


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
            {"forklift.domain": "f.example.com", "warehouse.domain": "w.example.com"},
            "f.example.com",
        ),
    ],
)
def test_forklifted(settings, expected_domain):
    request = pretend.stub(
        domain="example.com", registry=pretend.stub(settings=settings)
    )

    information_url = "TODO"

    resp = pypi.forklifted(request)

    assert resp.status_code == 410
    assert resp.status == (
        "410 This API has moved to https://{}/legacy/. See {} for more " "information."
    ).format(expected_domain, information_url)


def test_doap(pyramid_request):
    resp = pypi.doap(pyramid_request)

    assert resp.status_code == 410
    assert resp.status == "410 DOAP is no longer supported."


def test_forbidden_legacy():
    exc, request = pretend.stub(), pretend.stub()
    resp = pypi.forbidden_legacy(exc, request)
    assert resp is exc


def test_list_classifiers(db_request):
    ClassifierFactory.create(classifier="foo :: bar")
    ClassifierFactory.create(classifier="foo :: baz")
    ClassifierFactory.create(classifier="fiz :: buz")

    resp = pypi.list_classifiers(db_request)

    assert resp.status_code == 200
    assert resp.text == "fiz :: buz\nfoo :: bar\nfoo :: baz"


def test_search():
    term = pretend.stub()
    request = pretend.stub(
        params={"term": term},
        route_path=pretend.call_recorder(lambda *a, **kw: "/the/path"),
    )

    result = pypi.search(request)

    assert isinstance(result, HTTPMovedPermanently)
    assert result.headers["Location"] == "/the/path"
    assert result.status_code == 301
    assert request.route_path.calls == [pretend.call("search", _query={"q": term})]


class TestBrowse:
    def test_browse(self, db_request):
        classifier = ClassifierFactory.create(classifier="foo :: bar")

        db_request.params = {"c": str(classifier.id)}
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the/path")

        result = pypi.browse(db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == "/the/path"
        assert result.status_code == 301
        assert db_request.route_path.calls == [
            pretend.call("search", _query={"c": classifier.classifier})
        ]

    def test_browse_no_id(self):
        request = pretend.stub(params={})

        with pytest.raises(HTTPNotFound):
            pypi.browse(request)

    def test_browse_bad_id(self, db_request):
        db_request.params = {"c": "99999"}

        with pytest.raises(HTTPNotFound):
            pypi.browse(db_request)

    def test_brows_invalid_id(self, request):
        request = pretend.stub(params={"c": '7"'})

        with pytest.raises(HTTPNotFound):
            pypi.browse(request)


class TestFiles:
    def test_files(self, db_request):
        name = "pip"
        version = "10.0.0"

        db_request.params = {"name": name, "version": version}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: f"/project/{name}/{version}/#files"
        )

        result = pypi.files(db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == (f"/project/{name}/{version}/#files")
        assert result.status_code == 301
        assert db_request.route_path.calls == [
            pretend.call(
                "packaging.release", name=name, version=version, _anchor="files"
            )
        ]

    def test_files_no_version(self, db_request):
        name = "pip"

        db_request.params = {"name": name}

        with pytest.raises(HTTPNotFound):
            pypi.files(db_request)

    def test_files_no_name(self, db_request):
        version = "10.0.0"

        db_request.params = {"version": version}

        with pytest.raises(HTTPNotFound):
            pypi.files(db_request)


class TestDisplay:
    def test_display(self, db_request):
        name = "pip"
        version = "10.0.0"

        db_request.params = {"name": name, "version": version}
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: f"/project/{name}/{version}/"
        )

        result = pypi.display(db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == (f"/project/{name}/{version}/")
        assert result.status_code == 301
        assert db_request.route_path.calls == [
            pretend.call("packaging.release", name=name, version=version)
        ]

    def test_display_no_version(self, db_request):
        name = "pip"

        db_request.params = {"name": name}

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: f"/project/{name}/"
        )

        result = pypi.display(db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == (f"/project/{name}/")
        assert result.status_code == 301
        assert db_request.route_path.calls == [
            pretend.call("packaging.project", name=name)
        ]

    def test_display_no_name(self, db_request):
        version = "10.0.0"

        db_request.params = {"version": version}

        with pytest.raises(HTTPNotFound):
            pypi.display(db_request)


class TestToken:
    @pytest.mark.parametrize(
        ("project_name", "version", "valid"),
        [("foo", "1.0", True)],
    )
    def test_token_creation(
        self, db_request, macaroon_service, project_name, version, valid
    ):
        user = UserFactory.create()
        master_key, macaroon = macaroon_service.create_macaroon(
            "fake location",
            user.id,
            "fake description",
            {"version": 2, "permissions": "user"},
        )
        request = pretend.stub(
            user=user,
            domain="fake location",
            find_service=lambda interface, **kw: {IMacaroonService: macaroon_service}[
                interface
            ],
            master_key=master_key,
            project_name=project_name,
            version=version,
            description="fake description!",
        )
        assert isinstance(pypi.create_token(request), dict)
    
    def test_invalid_master_token(self, macaroon_service):
        user = UserFactory.create()
        request = pretend.stub(
            user=user,
            domain="fake location",
            find_service=lambda interface, **kw: {IMacaroonService: macaroon_service}[
                interface
            ],
            master_key="a fake key",
            project_name="foo",
            version="1.0",
            description="fake description!",
        )
        with pytest.raises(HTTPUnauthorized):
            pypi.create_token(request)