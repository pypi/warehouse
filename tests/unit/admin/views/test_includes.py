# SPDX-License-Identifier: Apache-2.0

from warehouse.admin.views import includes

from ....common.db.accounts import UserFactory
from ....common.db.organizations import OrganizationFactory
from ....common.db.packaging import ProjectFactory


def test_administer_project_include_returns_project(db_request):
    project = ProjectFactory.create()
    db_request.matchdict = {"project_name": project.name}
    assert includes.administer_project_include(db_request) == {
        "project": project,
        "prohibited": None,
        "project_name": project.name,
        "collisions": [],
    }


def test_administer_user_include_returns_user(db_request):
    user = UserFactory.create()
    assert includes.administer_user_include(user, db_request) == {"user": user}


def test_administer_organization_include_returns_organization(db_request):
    organization = OrganizationFactory.create()
    assert includes.administer_organization_include(organization, db_request) == {
        "organization": organization
    }
