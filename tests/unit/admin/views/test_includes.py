# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse.admin.views import includes

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


def test_administer_user_include_returns_user():
    user = pretend.stub()
    assert includes.administer_user_include(user, pretend.stub()) == {"user": user}
