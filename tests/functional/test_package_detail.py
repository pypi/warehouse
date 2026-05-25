# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from ..common.db.packaging import ProjectFactory, ReleaseFactory


def test_project_detail_uses_latest_release_badge_copy(webtest):
    project = ProjectFactory.create()
    ReleaseFactory.create(project=project, version="1.0")

    resp = webtest.get(f"/project/{project.name}/", status=HTTPStatus.OK)

    latest_badge = resp.html.find("a", class_="status-badge--good")
    assert latest_badge is not None
    assert latest_badge.get_text(strip=True) == "Latest release"
    assert "Latest version" not in resp.text
