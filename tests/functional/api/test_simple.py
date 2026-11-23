# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

import pytest

from inline_snapshot import snapshot
from pyramid.exceptions import PredicateMismatch
from pyramid.httpexceptions import HTTPForbidden, HTTPServiceUnavailable

from warehouse.api.simple import MIME_PYPI_SIMPLE_V1_JSON
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


@pytest.mark.parametrize("accept", ["text/html", MIME_PYPI_SIMPLE_V1_JSON])
def test_simple_missing_project(webtest, accept):
    path = "/simple/missing/"
    resp = webtest.get(path, headers={"Accept": accept}, status=404)
    assert resp.content_type == "application/problem+json"
    assert resp.json == {"status": 404, "title": "Not Found", "detail": path}
    assert resp.headers["Access-Control-Allow-Origin"] == "*"


@pytest.mark.parametrize(
    "error", [HTTPForbidden, PredicateMismatch, HTTPServiceUnavailable]
)
def test_simple_view_error(webtest, mocker, error):
    exc = error("Try again later.", headers={"Retry-After": "60"})
    mocker.patch("warehouse.api.simple._simple_index", side_effect=exc)
    resp = webtest.get("/simple/", status=exc.code)
    assert resp.json["detail"] == "Try again later."
    assert resp.headers["Retry-After"] == "60"


def test_similarly_named_paths_keep_html_errors(webtest):
    resp = webtest.get("/simple-other/", status=404)
    assert resp.content_type == "text/html"


def test_simple_unhandled_error(webtest, mocker, caplog):
    mocker.patch(
        "warehouse.api.simple._simple_index", side_effect=RuntimeError("secret")
    )
    resp = webtest.get("/simple/", status=500)
    assert resp.json["status"] == 500
    assert "secret" not in resp.text
    assert "secret" in caplog.text


def test_simple_malformed_path(webtest):
    resp = webtest.get("/simple/%FF/", status=400)
    assert resp.json["status"] == 400


def test_simple_mounted_method_not_allowed(webtest):
    resp = webtest.post(
        "/simple/", extra_environ={"SCRIPT_NAME": "/mirror"}, status=405
    )
    assert resp.json["status"] == 405
    assert resp.headers["Allow"] == "GET, HEAD, OPTIONS"


def test_simple_unsatisfiable_range(webtest):
    length = len(webtest.get("/simple/").body)
    headers = {"Range": f"bytes={length}-"}
    resp = webtest.get("/simple/", headers=headers, status=416)
    assert resp.content_type == "application/problem+json"
    assert resp.json["status"] == 416
    assert resp.headers["Content-Range"] == f"bytes */{length}"
    assert resp.headers["Cache-Control"] == "no-store"
    head = webtest.head("/simple/", headers=headers, status=416)
    assert head.body == b""
    assert head.content_length == len(resp.body)


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
<a href="http://localhost:7000/ff/99/ac93708f3e9a43aba8c212c4977480e2d47d38a5f56276ad70af7f2cbfb3/example2-1.0.0.tar.gz#sha256=a1dce4642866a610552fab0817cc7926f12d9ecc11f7016eb07bd5e721cee61e" data-requires-python="&gt;=3.14" >example2-1.0.0.tar.gz</a><br />
</body>
</html>
<!--SERIAL 0-->\
""")  # noqa: E501
