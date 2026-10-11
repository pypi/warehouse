# SPDX-License-Identifier: Apache-2.0

import pytest

from pyramid.httpexceptions import HTTPBadRequest, HTTPMovedPermanently, HTTPNotFound
from trove_classifiers import sorted_classifiers

from warehouse.legacy.api import pypi

from ....common.db.classifiers import ClassifierFactory


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
def test_forklifted(settings, expected_domain, pyramid_request):
    pyramid_request.domain = "example.com"
    pyramid_request.registry.settings.update(settings)

    information_url = "TODO"

    resp = pypi.forklifted(pyramid_request)

    assert resp.status_code == 410
    assert resp.status == (
        f"410 This API has moved to https://{expected_domain}/legacy/. "
        f"See {information_url} for more information."
    )


def test_doap(pyramid_request):
    resp = pypi.doap(pyramid_request)

    assert resp.status_code == 410
    assert resp.status == "410 DOAP is no longer supported."


def test_forbidden_legacy(mocker):
    exc = mocker.sentinel.exc
    resp = pypi.forbidden_legacy(exc, mocker.sentinel.request)
    assert resp is exc


def test_list_classifiers(db_request):
    resp = pypi.list_classifiers(db_request)

    assert resp.status_code == 200
    assert resp.text == "\n".join(sorted_classifiers)


def test_search(pyramid_request, mocker):
    term = mocker.sentinel.term
    pyramid_request.params = {"term": term}
    route_path = mocker.patch.object(
        pyramid_request, "route_path", autospec=True, return_value="/the/path"
    )

    result = pypi.search(pyramid_request)

    assert isinstance(result, HTTPMovedPermanently)
    assert result.headers["Location"] == "/the/path"
    assert result.status_code == 301
    route_path.assert_called_once_with("search", _query={"q": term})


class TestBrowse:
    def test_browse(self, db_request, mocker):
        classifier = ClassifierFactory.create(classifier="foo :: bar")

        db_request.params = {"c": str(classifier.id)}
        route_path = mocker.patch.object(
            db_request, "route_path", autospec=True, return_value="/the/path"
        )

        result = pypi.browse(db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == "/the/path"
        assert result.status_code == 301
        route_path.assert_called_once_with(
            "search", _query={"c": classifier.classifier}
        )

    def test_browse_no_id(self, pyramid_request):
        pyramid_request.params = {}

        with pytest.raises(HTTPNotFound):
            pypi.browse(pyramid_request)

    def test_browse_bad_id(self, db_request):
        db_request.params = {"c": "99999"}

        with pytest.raises(HTTPNotFound):
            pypi.browse(db_request)

    def test_brows_invalid_id(self, pyramid_request):
        pyramid_request.params = {"c": '7"'}

        with pytest.raises(HTTPNotFound):
            pypi.browse(pyramid_request)


class TestFiles:
    def test_files(self, db_request, mocker):
        name = "pip"
        version = "10.0.0"

        db_request.params = {"name": name, "version": version}
        route_path = mocker.patch.object(
            db_request,
            "route_path",
            autospec=True,
            return_value=f"/project/{name}/{version}/#files",
        )

        result = pypi.files(db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == (f"/project/{name}/{version}/#files")
        assert result.status_code == 301
        route_path.assert_called_once_with(
            "packaging.release", name=name, version=version, _anchor="files"
        )

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
    def test_display(self, db_request, mocker):
        name = "pip"
        version = "10.0.0"

        db_request.params = {"name": name, "version": version}
        route_path = mocker.patch.object(
            db_request,
            "route_path",
            autospec=True,
            return_value=f"/project/{name}/{version}/",
        )

        result = pypi.display(db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == (f"/project/{name}/{version}/")
        assert result.status_code == 301
        route_path.assert_called_once_with(
            "packaging.release", name=name, version=version
        )

    def test_display_no_version(self, db_request, mocker):
        name = "pip"

        db_request.params = {"name": name}

        route_path = mocker.patch.object(
            db_request, "route_path", autospec=True, return_value=f"/project/{name}/"
        )

        result = pypi.display(db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == (f"/project/{name}/")
        assert result.status_code == 301
        route_path.assert_called_once_with("packaging.project", name=name)

    def test_display_no_name(self, db_request):
        version = "10.0.0"

        db_request.params = {"version": version}

        with pytest.raises(HTTPNotFound):
            pypi.display(db_request)
