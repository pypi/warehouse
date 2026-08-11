# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from warehouse.api.simple import MIME_PYPI_SIMPLE_V1_JSON
from inline_snapshot import snapshot

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

    project = ProjectFactory.create(name="example")
    release = ReleaseFactory.create(project=project, version="1.0.0")
    FileFactory.create(
        filename="example-1.0.0.tar.gz", release=release, packagetype="sdist"
    )

    resp = webtest.get(f"/simple/{project.normalized_name}/", status=HTTPStatus.OK)

    assert resp.text == snapshot("""\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta name="pypi:repository-version" content="1.4">
<meta name="pypi:project-status" content="active">    <title>Links for example</title>
  </head>
  <body>
    <h1>Links for example</h1>
<a href="http://localhost:7000/#sha256=7e657eb56fc128fcfbbc8c6c613f4b67ae589e93871c96aeb502754bbf24987f" >example-1.0.0.tar.gz</a><br />
</body>
</html>
<!--SERIAL 0-->\
""")  # noqa: E501
