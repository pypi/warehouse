# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from warehouse.api.simple import MIME_PYPI_SIMPLE_V1_JSON

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
