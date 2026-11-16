# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

import pytest

from tests.common.db.organizations import (
    OrganizationFactory,
    OrganizationNameCatalogFactory,
)


def test_org_profile(webtest):
    # Create an org
    org = OrganizationFactory.create()
    assert org.name
    # ...and verify that the org's profile page exists
    resp = webtest.get(f"/org/{org.name}/")
    assert resp.status_code == HTTPStatus.OK


@pytest.mark.parametrize("path", ["/org/{}/", "/manage/organization/{}/settings/"])
def test_renamed_org_redirects(webtest, path):
    org = OrganizationFactory.create(name="newname")
    OrganizationNameCatalogFactory.create(
        normalized_name="oldname", organization_id=org.id
    )

    resp = webtest.get(path.format("oldname"))

    assert resp.status_code == HTTPStatus.PERMANENT_REDIRECT
    assert resp.location == "http://localhost" + path.format("newname")
