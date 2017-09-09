# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import shlex

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy import or_
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.packaging.models import Project, Role, JournalEntry
from warehouse.utils.paginate import paginate_url_factory


@view_config(
    route_name="admin.project.list",
    renderer="admin/projects/list.html",
    permission="admin",
    uses_session=True,
)
def project_list(request):
    q = request.params.get("q")

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    projects_query = request.db.query(Project).order_by(Project.name)

    if q:
        terms = shlex.split(q)

        filters = []
        for term in terms:
            filters.append(Project.name.ilike(term))

        projects_query = projects_query.filter(or_(*filters))

    projects = SQLAlchemyORMPage(
        projects_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"projects": projects, "query": q}


@view_config(route_name="admin.project.detail",
             renderer="admin/projects/detail.html",
             permission="admin",
             uses_session=True,
             require_csrf=True,
             require_methods=False)
def project_detail(request):
    try:
        project = (
            request.db.query(Project)
            .filter(
                Project.normalized_name ==
                request.matchdict["project_name"]
            )
            .one()
        )
        maintainers = [
            (r.user, r.role_name)
            for r in (
                request.db.query(Role)
                .join(User)
                .filter(Role.project == project)
                .distinct(User.username)
                .order_by(User.username)
                .all()
            )
        ]
        journal = [
            entry
            for entry in (
                request.db.query(JournalEntry)
                .filter(JournalEntry.name == project.normalized_name)
                .order_by(JournalEntry.submitted_date.desc())
                .all()
            )
        ]
    except NoResultFound:
        raise HTTPNotFound

    return {"project": project, "maintainers": maintainers, "journal": journal}
