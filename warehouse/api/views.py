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

import datetime
from packaging.version import parse

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.view import view_config
from sqlalchemy import func, orm

from warehouse.packaging import models
from warehouse.utils.paginate import paginate_url_factory
from warehouse.api import schema
from warehouse.api import spec
from warehouse.api.utils import pagination_serializer

# Should this move to a config?
ITEMS_PER_PAGE = 100


@view_config(route_name="api.spec", renderer="json")
def api_spec(request):
    return spec.hypermedia_spec.to_dict()


@view_config(route_name="api.views.projects", renderer="json")
def projects(request):
    """
    Return a paginated list of all projects, serialized minimally.

    Replaces simple API: /simple/
    Replaces XML-RPC: list_packages()

    Filters:
        serial_since: Limits the response to projects that have been updated
                      since the provided serial.
        page_num: Specifies the page to start with. If not provided, the
                  response begins at page 1.
    """
    serial_since = request.params.get("serial_since")
    serial = request.params.get("serial")

    page_num = int(request.params.get("page", 1))
    query = request.db.query(models.Project).order_by(models.Project.created)

    if serial_since:
        query = query.filter(models.Project.last_serial >= serial_since)
    if serial:
        query = query.filter(models.Project.last_serial == serial)

    projects_page = SQLAlchemyORMPage(
        query,
        page=page_num,
        items_per_page=ITEMS_PER_PAGE,
        url_maker=paginate_url_factory(request),
    )
    project_schema = schema.Project(
        only=("last_serial", "normalized_name", "url", "legacy_project_json"), many=True
    )
    project_schema.context = {"request": request}
    return pagination_serializer(
        project_schema, projects_page, "api.views.projects", request
    )


@view_config(
    route_name="api.views.projects.detail", renderer="json", context=models.Project
)
def projects_detail(project, request):
    """
    Returns a detail view of a single project.
    """
    project_schema = schema.Project()
    project_schema.context = {"request": request}
    return project_schema.dump(project)


@view_config(
    route_name="api.views.projects.detail.files",
    renderer="json",
    context=models.Project,
)
def projects_detail_files(project, request):
    files = sorted(
        request.db.query(models.File)
        .options(orm.joinedload(models.File.release))
        .filter(
            models.File.name == project.name,
            models.File.version.in_(
                request.db.query(models.Release)
                .filter(models.Release.project == project)
                .with_entities(models.Release.version)
            ),
        )
        .all(),
        key=lambda f: (parse(f.version), f.filename),
    )
    serializer = schema.File(many=True, only=("filename", "url"))
    serializer.context = {"request": request}
    return serializer.dump(files)


@view_config(
    route_name="api.views.projects.releases", renderer="json", context=models.Project
)
def project_releases(project, request):
    releases = (
        request.db.query(models.Release)
        .filter(models.Release.project == project)
        .order_by(
            models.Release.is_prerelease.nullslast(),
            models.Release._pypi_ordering.desc(),
        )
        .all()
    )
    serializer = schema.Release(many=True, only=("version", "url"))
    serializer.context = {"request": request}
    return serializer.dump(releases)


@view_config(route_name="api.views.projects.releases.detail", renderer="json")
def releases_detail(release, request):

    project = release.project
    try:
        release = (
            request.db.query(models.Release)
            .options(orm.undefer("description"))
            .join(models.Project)
            .filter(
                (
                    models.Project.normalized_name
                    == func.normalize_pep426_name(project.name)
                )
                & (models.Release.version == release.version)
            )
            .one()
        )
    except orm.exc.NoResultFound:
        return {}
    serializer = schema.Release()
    serializer.context = {"request": request}
    return serializer.dump(release)


@view_config(route_name="api.views.projects.releases.files", renderer="json")
def releases_detail_files(release, request):

    project = release.project
    files = (
        request.db.query(models.File)
        .join(models.Release)
        .join(models.Project)
        .filter(
            (models.Project.normalized_name == func.normalize_pep426_name(project.name))
        )
        .order_by(models.Release._pypi_ordering.desc(), models.File.filename)
        .all()
    )
    serializer = schema.File(many=True)
    serializer.context = {"request": request}
    return serializer.dump(files)


@view_config(route_name="api.views.projects.detail.roles", renderer="json")
def projects_detail_roles(project, request):
    roles = (
        request.db.query(models.Role)
        .join(models.User, models.Project)
        .filter(
            models.Project.normalized_name == func.normalize_pep426_name(project.name)
        )
        .order_by(models.Role.role_name.desc(), models.User.username)
        .all()
    )
    serializer = schema.Role(many=True)
    return serializer.dump(roles)


@view_config(route_name="api.views.journals", renderer="json")
def journals(request):
    since = request.params.get("since")
    updated_releases = request.params.get("updated_releases")
    page_num = int(request.params.get("page", 1))
    query = request.db.query(models.JournalEntry).order_by(
        models.JournalEntry.submitted_date
    )

    if updated_releases:
        query = query.filter(models.JournalEntry.version.isnot(None))

    if since:
        query = query.filter(
            models.JournalEntry.submitted_date
            > datetime.datetime.utcfromtimestamp(int(since))
        )

    journals_page = SQLAlchemyORMPage(
        query,
        page=page_num,
        items_per_page=ITEMS_PER_PAGE,
        url_maker=paginate_url_factory(request),
    )
    serializer = schema.Journal(many=True)
    serializer.context = {"request": request}
    return pagination_serializer(
        serializer, journals_page, "api.views.journals", request
    )


@view_config(route_name="api.views.journals.latest", renderer="json")
def journals_latest(request):
    last_serial = request.db.query(func.max(models.JournalEntry.id)).scalar()
    response = {
        "last_serial": last_serial,
        "project_url": request.route_url(
            "api.views.projects", _query={"serial": last_serial}
        ),
    }
    return response


@view_config(route_name="api.views.users.details.projects", renderer="json")
def user_detail_packages(user, request):
    roles = (
        request.db.query(models.Role)
        .join(models.User, models.Project)
        .filter(models.User.username == user.username)
        .order_by(models.Role.role_name.desc(), models.Project.name)
        .all()
    )
    serializer = schema.UserProjects(many=True)
    serializer.context["request"] = request
    return serializer.dump(roles)
