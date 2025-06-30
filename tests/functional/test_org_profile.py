# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus

from tests.common.db.organizations import OrganizationFactory


def test_org_profile(webtest):
    # Create an org
    org = OrganizationFactory.create()
    assert org.name
    # ...and verify that the org's profile page exists
    resp = webtest.get(f"/org/{org.name}/")
    assert resp.status_code == HTTPStatus.OK
