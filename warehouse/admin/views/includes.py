# SPDX-License-Identifier: Apache-2.0

from pyramid.view import view_config
from sqlalchemy import func, select

from warehouse.accounts.models import User
from warehouse.packaging.models import ProhibitedProjectName, Project


@view_config(
    route_name="includes.administer-project-include",
    renderer="includes/admin/administer-project-include.html",
    uses_session=True,
)
def administer_project_include(request):
    project_name = request.matchdict.get("project_name")
    project = (
        request.db.query(Project)
        .filter(Project.normalized_name == func.normalize_pep426_name(project_name))
        .one_or_none()
    )
    prohibited = (
        request.db.query(ProhibitedProjectName)
        .filter(ProhibitedProjectName.name == func.normalize_pep426_name(project_name))
        .one_or_none()
    )
    collisions = request.db.scalars(
        select(Project.name)
        .filter(
            func.ultranormalize_name(Project.name)
            == func.ultranormalize_name(project_name)
        )
        .filter(
            func.normalize_pep426_name(Project.name)
            != func.normalize_pep426_name(project_name)
        )
    ).all()

    return {
        "project": project,
        "project_name": project_name,
        "prohibited": prohibited,
        "collisions": collisions,
    }


@view_config(
    route_name="includes.administer-user-include",
    context=User,
    renderer="includes/admin/administer-user-include.html",
    uses_session=True,
)
def administer_user_include(user, request):
    return {"user": user}
