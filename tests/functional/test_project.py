# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from tests.common.db.packaging import FileFactory, ProjectFactory, ReleaseFactory


def test_project_release_file_details_links_to_inspector(webtest):
    project = ProjectFactory.create(name="sampleproject")
    release = ReleaseFactory.create(project=project, version="1.2.3")
    file = FileFactory.create(
        release=release,
        filename=f"{project.name}-{release.version}.tar.gz",
        packagetype="sdist",
        python_version="source",
    )

    response = webtest.get(
        f"/project/{project.normalized_name}/{release.version}/", status=HTTPStatus.OK
    )

    inspector_url = (
        f"https://inspector.pypi.io/project/{project.normalized_name}/"
        f"{release.version}/packages/{file.path}/"
    )
    inspector_link = response.html.find("a", {"href": inspector_url})

    assert inspector_link is not None
    assert inspector_link.text == "View in Inspector"
