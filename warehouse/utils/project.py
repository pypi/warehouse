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

from warehouse.packaging.interfaces import IDocsStorage
from warehouse.packaging.models import JournalEntry
from warehouse.tasks import task


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
        request.session.flash("Confirm the request", queue="error")
        raise HTTPSeeOther(request.route_path(fail_route, project_name=project_name))
    if canonicalize_name(confirm) != project.normalized_name:
        request.session.flash(
            "Could not delete project - "
            + f"{confirm!r} is not the same as {project.normalized_name!r}",
            queue="error",
        )
        raise HTTPSeeOther(request.route_path(fail_route, project_name=project_name))


def destroy_project(project, request):
    """
    This permanently removes the project and everything belonging to it.
    Only for use by administrative routes.
    """

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

    request.session.flash(f"Destroyed the project {project.name!r}", queue="success")


def _soft_restore_file(file_):
    file_.soft_deleted = False


def _soft_restore_release(release):
    release.soft_deleted = False
    for file_ in release.files:
        _soft_restore_file(file_)


def _soft_restore_project(project):
    project.soft_deleted = False
    for release in project.releases:
        _soft_restore_release(release)

def soft_restore_project(project, request):

    request.db.add(
        JournalEntry(
            name=project.name,
            action="restore project",
            submitted_by=request.user,
            submitted_from=request.remote_addr,
        )
    )

    _soft_restore_project(project)

    request.db.flush()

    request.session.flash(f"Restored the project {project.name!r}", queue="success")



def destroy_docs(project, request):
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

    request.session.flash(f"Deleted docs for project {project.name!r}", queue="success")

