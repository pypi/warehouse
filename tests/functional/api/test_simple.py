# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

import pytest

from inline_snapshot import snapshot
from pyramid.exceptions import PredicateMismatch
from pyramid.httpexceptions import (
    HTTPForbidden,
    HTTPMethodNotAllowed,
    HTTPServiceUnavailable,
)

from warehouse.api.integrity import MIME_PYPI_INTEGRITY_V1_JSON
from warehouse.api.simple import (
    MIME_PYPI_SIMPLE_V1_HTML,
    MIME_PYPI_SIMPLE_V1_JSON,
    MIME_TEXT_HTML,
)
from warehouse.packaging.models import LifecycleStatus

from ...common.db.packaging import (
    FileFactory,
    ProjectFactory,
    ProvenanceFactory,
    ReleaseFactory,
)


def test_simple_api_html(webtest):
    resp = webtest.get("/simple/", status=HTTPStatus.OK)

    assert resp.content_type == "text/html"
    assert "X-PyPI-Last-Serial" in resp.headers


def test_simple_api_json(webtest):
    resp = webtest.get(
        "/simple/",
        headers={"Accept": MIME_PYPI_SIMPLE_V1_JSON},
        status=HTTPStatus.OK,
    )

    assert resp.content_type == MIME_PYPI_SIMPLE_V1_JSON
    assert resp.body.endswith(b"\n")
    assert "projects" in resp.json


def test_simple_api_detail(webtest):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    FileFactory.create_batch(2, release=release, packagetype="bdist_wheel")

    resp = webtest.get(f"/simple/{project.normalized_name}/", status=HTTPStatus.OK)

    assert resp.content_type == "text/html"
    assert "X-PyPI-Last-Serial" in resp.headers
    assert resp.html.h1.string == f"Links for {project.normalized_name}"
    # There should be a link for every file
    assert len(resp.html.find_all("a")) == 2


def test_simple_api_detail_json(webtest):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    FileFactory.create(release=release, packagetype="bdist_wheel")

    resp = webtest.get(
        f"/simple/{project.normalized_name}/",
        headers={"Accept": MIME_PYPI_SIMPLE_V1_JSON},
        status=HTTPStatus.OK,
    )

    assert resp.content_type == MIME_PYPI_SIMPLE_V1_JSON
    assert resp.body.endswith(b"\n")
    assert resp.json["name"] == project.normalized_name
    assert len(resp.json["files"]) == 1


@pytest.mark.parametrize(
    "accept",
    [None, MIME_TEXT_HTML, MIME_PYPI_SIMPLE_V1_HTML, MIME_PYPI_SIMPLE_V1_JSON],
)
def test_pep847_simple_api_not_found(webtest, accept):
    path = "/simple/nonexistent-project/"
    headers = {} if accept is None else {"Accept": accept}

    resp = webtest.get(path, headers=headers, status=HTTPStatus.NOT_FOUND)

    assert resp.content_type == "application/problem+json"
    assert resp.json == {
        "status": HTTPStatus.NOT_FOUND,
        "title": "Not Found",
        "detail": path,
    }
    assert resp.headers["Access-Control-Allow-Origin"] == "*"


@pytest.mark.parametrize("accept", [MIME_TEXT_HTML, MIME_PYPI_SIMPLE_V1_JSON])
@pytest.mark.parametrize(
    ("path", "helper", "detail"),
    [
        ("/simple/", "_simple_index", None),
        (
            "/simple/example/",
            "_simple_detail",
            "The project index is temporarily unavailable.",
        ),
    ],
)
def test_pep847_simple_api_server_error(webtest, mocker, accept, path, helper, detail):
    ProjectFactory.create(name="example")
    failing_helper = mocker.patch(
        f"warehouse.api.simple.{helper}",
        side_effect=HTTPServiceUnavailable(
            detail=detail,
            headers={"Retry-After": "60"},
        ),
    )

    resp = webtest.get(
        path,
        headers={"Accept": accept},
        status=HTTPStatus.SERVICE_UNAVAILABLE,
    )

    failing_helper.assert_called_once()
    assert resp.content_type == "application/problem+json"
    assert resp.json == {
        "status": HTTPStatus.SERVICE_UNAVAILABLE,
        "title": "Service Unavailable",
        "detail": detail or HTTPServiceUnavailable.explanation,
    }
    assert resp.headers["Retry-After"] == "60"
    assert resp.headers["Access-Control-Allow-Origin"] == "*"


@pytest.mark.parametrize("accept", [MIME_TEXT_HTML, MIME_PYPI_SIMPLE_V1_JSON])
@pytest.mark.parametrize(
    ("path", "helper"),
    [("/simple/", "_simple_index"), ("/simple/example/", "_simple_detail")],
)
@pytest.mark.parametrize(
    ("exception", "status", "title"),
    [
        (HTTPForbidden, HTTPStatus.FORBIDDEN, "Forbidden"),
        (PredicateMismatch, HTTPStatus.NOT_FOUND, "Not Found"),
    ],
)
def test_pep847_simple_api_client_error(
    webtest, mocker, accept, path, helper, exception, status, title
):
    ProjectFactory.create(name="example")
    detail = "The requested index is unavailable."
    failing_helper = mocker.patch(
        f"warehouse.api.simple.{helper}", side_effect=exception(detail=detail)
    )

    resp = webtest.get(path, headers={"Accept": accept}, status=status)

    failing_helper.assert_called_once()
    assert resp.content_type == "application/problem+json"
    assert resp.json == {"status": status, "title": title, "detail": detail}
    assert "Location" not in resp.headers


@pytest.mark.parametrize("accept", [MIME_TEXT_HTML, MIME_PYPI_SIMPLE_V1_JSON])
@pytest.mark.parametrize("path", ["/simple/", "/simple/example/"])
def test_pep847_simple_api_method_not_allowed(webtest, accept, path):
    ProjectFactory.create(name="example")

    resp = webtest.post(
        path,
        headers={"Accept": accept},
        status=HTTPStatus.METHOD_NOT_ALLOWED,
    )

    assert resp.content_type == "application/problem+json"
    assert resp.json == {
        "status": HTTPStatus.METHOD_NOT_ALLOWED,
        "title": "Method Not Allowed",
        "detail": HTTPMethodNotAllowed.explanation,
    }
    assert resp.headers["Allow"] == "GET, HEAD, OPTIONS"


@pytest.mark.parametrize("accept", [MIME_TEXT_HTML, MIME_PYPI_SIMPLE_V1_JSON])
def test_pep847_simple_api_redirect_unchanged(webtest, accept):
    project = ProjectFactory.create(name="Example_Package")

    resp = webtest.get(
        f"/simple/{project.name}/",
        headers={"Accept": accept},
        status=HTTPStatus.MOVED_PERMANENTLY,
    )

    assert resp.location == f"http://localhost/simple/{project.normalized_name}/"
    assert resp.content_type != "application/problem+json"


@pytest.mark.parametrize(
    "path",
    [
        "/pypi/nonexistent-project/json",
        "/pypi/nonexistent-project/1.0/json",
    ],
)
def test_pep847_legacy_json_not_found_unchanged(webtest, path):
    resp = webtest.get(path, status=HTTPStatus.NOT_FOUND)

    assert resp.content_type == "application/json"
    assert resp.json == {"message": "Not Found"}


def test_pep847_integrity_not_found_unchanged(webtest):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    file = FileFactory.create(release=release, packagetype="sdist")

    resp = webtest.get(
        f"/integrity/{project.normalized_name}/{release.version}/"
        f"{file.filename}/provenance",
        headers={"Accept": MIME_PYPI_INTEGRITY_V1_JSON},
        status=HTTPStatus.NOT_FOUND,
    )

    assert resp.content_type == "application/json"
    assert resp.json == {"message": f"No provenance available for {file.filename}"}


@pytest.mark.parametrize(
    "path", ["/project/nonexistent-project/", "/simple-not-an-api/"]
)
def test_pep847_other_not_found_unchanged(webtest, path):
    resp = webtest.get(
        path,
        headers={"Accept": MIME_PYPI_SIMPLE_V1_JSON},
        status=HTTPStatus.NOT_FOUND,
    )

    assert resp.content_type == "text/html"
    assert "Page Not Found (404)" in resp.html.title.text


def test_simple_api_has_provenance(webtest):
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)
    files = FileFactory.create_batch(2, release=release, packagetype="bdist_wheel")

    for file in files:
        ProvenanceFactory.create(file=file)

    resp = webtest.get(f"/simple/{project.normalized_name}/", status=HTTPStatus.OK)
    links = resp.html.find_all("a")

    for file in files:
        link = next(link for link in links if link.text == file.filename)
        provenance_url = link.get("data-provenance")

        assert provenance_url == (
            f"http://localhost/integrity/{file.release.project.normalized_name}/"
            f"{file.release.version}/{file.filename}/provenance"
        )


def test_pep833_simple_api_base_html_frozen(webtest):
    """
    WARNING! PEP 833 freezes the HTML representation of the simple API;
    this test backstops that freeze by ensuring that we don't accidentally
    the HTML representation.

    If you're *intentionally* changing the HTML representation, even
    just the whitespace, make sure you have a good reason for doing do!
    """

    resp = webtest.get("/simple/", status=HTTPStatus.OK)

    assert resp.text == snapshot("""\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta name="pypi:repository-version" content="1.4">
    <title>Simple index</title>
  </head>
  <body>
</body>
</html>\
""")


def test_pep833_simple_api_detail_html_frozen(webtest):
    """
    WARNING! PEP 833 freezes the HTML representation of the simple API;
    this test backstops that freeze by ensuring that we don't accidentally
    the HTML representation.

    If you're *intentionally* changing the HTML representation, even
    just the whitespace, make sure you have a good reason for doing do!
    """

    project = ProjectFactory.create(
        name="example2",
        lifecycle_status=LifecycleStatus.Archived,
    )
    release = ReleaseFactory.create(
        project=project, version="1.0.0", requires_python=">=3.14"
    )
    FileFactory.create(
        filename="example2-1.0.0.tar.gz", release=release, packagetype="sdist"
    )

    resp = webtest.get(f"/simple/{project.normalized_name}/", status=HTTPStatus.OK)

    assert resp.text == snapshot("""\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta name="pypi:repository-version" content="1.4">
<meta name="pypi:project-status" content="archived">    <title>Links for example2</title>
  </head>
  <body>
    <h1>Links for example2</h1>
<a href="http://localhost:7000/#sha256=a1dce4642866a610552fab0817cc7926f12d9ecc11f7016eb07bd5e721cee61e" data-requires-python="&gt;=3.14" >example2-1.0.0.tar.gz</a><br />
</body>
</html>
<!--SERIAL 0-->\
""")  # noqa: E501
