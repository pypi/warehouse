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

from packaging.utils import canonicalize_name
from pyramid.httpexceptions import HTTPSeeOther

from warehouse.packaging.models import (
    Project, Release, Dependency, File, Role, JournalEntry, release_classifiers
)


def confirm_project(project, request, fail_route):
    confirm = request.POST.get("confirm")
    project_name = project.normalized_name
    if not confirm:
        request.session.flash(
            "Must confirm the request.",
            queue="error",
        )
        raise HTTPSeeOther(
            request.route_path(fail_route, project_name=project_name)
        )
    if canonicalize_name(confirm) != project.normalized_name:
        request.session.flash(
            "Could not delete project - " +
            f"{confirm!r} is not the same as {project.normalized_name!r}",
            queue="error",
        )
        raise HTTPSeeOther(
            request.route_path(fail_route, project_name=project_name)
        )


def remove_project(project, request):
    # TODO: We don't actually delete files from the data store. We should add
    #       some kind of garbage collection at some point.

    request.db.add(
        JournalEntry(
            name=project.name,
            action="remove",
            submitted_by=request.user,
            submitted_from=request.remote_addr,
        )
    )
    request.db.query(Role).filter(Role.project == project).delete()
    request.db.query(File).filter(File.name == project.name).delete()
    (request.db.query(Dependency).filter(Dependency.name == project.name)
               .delete())
    (request.db.execute(release_classifiers.delete()
                        .where(release_classifiers.c.name ==
                               project.name)))

    # Load the following objects into the session and individually delete them
    # so they are included in `session.deleted` and their cache keys are purged

    # Delete releases first, otherwise they will get cascade-deleted by the
    # project deletion and won't be purged
    for release in (
            request.db.query(Release)
            .filter(Release.name == project.name)
            .all()):
        request.db.delete(release)

    # Finally, delete the project
    request.db.delete(
        request.db.query(Project).filter(Project.name == project.name).one()
    )

    request.session.flash(
        f"Successfully deleted the project {project.name!r}.",
        queue="success",
    )
