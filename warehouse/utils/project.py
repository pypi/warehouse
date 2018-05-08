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

from warehouse.tasks import task
from warehouse.packaging.interfaces import IDocsStorage
from warehouse.packaging.models import JournalEntry


@task(bind=True, ignore_result=True, acks_late=True)
def remove_documentation(task, request, project_name):
    request.log.info("Removing documentation for %s", project_name)
    storage = request.find_service(IDocsStorage)
    try:
        storage.remove_by_prefix(project_name)
    except Exception as exc:
        task.retry(exc=exc)


def confirm_project(project, request, fail_route):
    confirm = request.POST.get("confirm_project_name")
    project_name = project.normalized_name
    if not confirm:
        request.session.flash(
            "Must confirm the request",
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


def remove_project(project, request, flash=True):
    # TODO: We don't actually delete files from the data store. We should add
    #       some kind of garbage collection at some point.

    request.db.add(
        JournalEntry(
            name=project.name,
            action="remove project",
            submitted_by=request.user,
            submitted_from=request.remote_addr,
        )
    )

    request.db.delete(project)

    # Flush so we can repeat this multiple times if necessary
    request.db.flush()

    if flash:
        request.session.flash(
            f"Successfully deleted the project {project.name!r}",
            queue="success",
        )


def destroy_docs(project, request, flash=True):
    request.db.add(
        JournalEntry(
            name=project.name,
            action="docdestroy",
            submitted_by=request.user,
            submitted_from=request.remote_addr,
        )
    )

    request.task(remove_documentation).delay(project.name)

    project.has_docs = False

    if flash:
        request.session.flash(
            f"Successfully deleted docs for project {project.name!r}",
            queue="success",
        )
