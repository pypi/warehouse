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
import typing

from natsort import natsorted
from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.authnz import Permissions
from warehouse.cache.origin import origin_cache
from warehouse.observations.models import ObservationKind
from warehouse.packaging.forms import SubmitMalwareObservationForm
from warehouse.packaging.models import Description, File, Project, Release, Role

if typing.TYPE_CHECKING:
    import pypi_attestations


@view_config(
    route_name="packaging.project",
    context=Project,
    renderer="packaging/detail.html",
    decorator=[
        origin_cache(
            1 * 24 * 60 * 60, stale_if_error=5 * 24 * 60 * 60  # 1 day, 5 days stale
        )
    ],
    has_translations=True,
)
def project_detail(project, request):
    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(request.current_route_path(name=project.name))

    try:
        release = (
            request.db.query(Release)
            .filter(Release.project == project)
            .order_by(
                Release.yanked,
                Release.is_prerelease.nullslast(),
                Release._pypi_ordering.desc(),
            )
            .limit(1)
            .one()
        )
    except NoResultFound:
        raise HTTPNotFound

    return release_detail(release, request)


def format_url(base_url: str, reference: str):
    """Format a URL to create a permalink to a repository.

    Works on both GitHub and GitLab.
    Reference can either be a hash or a named revision.
    """
    return f"{base_url}/tree/{reference}"


def get_publication_details(
    claims: dict[str, str], publisher: pypi_attestations.Publisher
):
    """Helper function for Jinja to format the claims present in the attestation."""
    workflow_filename = ""
    if publisher.kind == "GitHub":
        workflow_filename = publisher.workflow
    elif publisher.kind == "GitLab":
        workflow_filename = publisher.workflow_filepath

    # Source Repository URI
    repo_url = claims.get("1.3.6.1.4.1.57264.1.12", "")
    # Build Config URI
    workflow_url = claims.get("1.3.6.1.4.1.57264.1.18", "")
    # Build Config Digest
    build_hash = claims.get("1.3.6.1.4.1.57264.1.19", "")

    # The claim `workflow_url` does not return a valid link to the repository,
    # but we can use it to retrieve the path towards the workflow file.
    workflow_file_path = workflow_url.split("@")[0].replace(repo_url + "/", "")

    workflow_permalink = f"{repo_url}/blob/{build_hash}/{workflow_file_path}"

    return {
        "workflow_url": workflow_permalink,
        "workflow_filename": workflow_filename,
        "build_hash": build_hash,
        # Issuer
        "issuer": claims.get("1.3.6.1.4.1.57264.1.8"),
        # Runner Environment
        "environment": claims.get("1.3.6.1.4.1.57264.1.11"),
        # Source Repository URI
        "source": claims.get("1.3.6.1.4.1.57264.1.12"),
        # Source Repository Digest
        "source_digest": claims.get("1.3.6.1.4.1.57264.1.13"),
        # Source Repository Ref
        "source_ref": claims.get("1.3.6.1.4.1.57264.1.14"),
        # Source Repository Owner URI
        "owner": claims.get("1.3.6.1.4.1.57264.1.16"),
        # Build Trigger
        "trigger": claims.get("1.3.6.1.4.1.57264.1.20"),
        # Source Repository Visibility At Signing
        "access": claims.get("1.3.6.1.4.1.57264.1.22"),
    }


@view_config(
    route_name="packaging.release",
    context=Release,
    renderer="packaging/detail.html",
    decorator=[
        origin_cache(
            1 * 24 * 60 * 60, stale_if_error=5 * 24 * 60 * 60  # 1 day, 5 days stale
        )
    ],
    has_translations=True,
)
def release_detail(release, request):
    project = release.project

    # Check if the requested version is equivalent but not exactly the same as
    # the release's version. Use `.get` because this view is used by
    # `project_detail` and there may not be a version.
    #
    # This also handles the case where both the version and the project name
    # need adjusted, and handles it in a single redirect.
    if release.version != request.matchdict.get("version", release.version):
        return HTTPMovedPermanently(
            request.current_route_path(name=project.name, version=release.version)
        )

    # It's possible that the requested version was correct (or not provided),
    # but we still need to adjust the project name.
    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(request.current_route_path(name=project.name))

    # Grab the rendered description
    description_html = (
        request.db.query(Description.html)
        .filter(Description.id == release.description_id)
        .one()
        .html
    )

    # Get all of the maintainers for this project.
    maintainers = [
        r.user
        for r in (
            request.db.query(Role)
            .join(User)
            .filter(Role.project == project)
            .distinct(User.username)
            .order_by(User.username)
            .all()
        )
    ]

    # Get the license from both the `Classifier` and `License` metadata fields
    license_classifiers = ", ".join(
        c.split(" :: ")[-1] for c in release.classifiers if c.startswith("License")
    )

    # Make a best effort when the entire license text is given by using the
    # first line only.
    short_license = release.license.split("\n")[0] if release.license else None

    # Truncate the short license if we were unable to shorten it with newlines
    if short_license and len(short_license) > 100 and short_license == release.license:
        short_license = short_license[:100] + "..."

    if license_classifiers and short_license:
        license = f"{license_classifiers} ({short_license})"
    else:
        license = license_classifiers or short_license or None

    # We cannot easily sort naturally in SQL, sort here and pass to template
    sdists = natsorted(
        release.files.filter(File.packagetype == "sdist").all(),
        reverse=True,
        key=lambda f: f.filename,
    )
    bdists = natsorted(
        release.files.filter(File.packagetype != "sdist").all(),
        reverse=True,
        key=lambda f: f.filename,
    )

    return {
        "project": project,
        "release": release,
        "description": description_html,
        "files": sdists + bdists,
        "sdists": sdists,
        "bdists": bdists,
        "latest_version": project.latest_version,
        "all_versions": project.all_versions,
        "maintainers": maintainers,
        "license": license,
        # Additional function to format the attestations
        "get_publication_details": get_publication_details,
        "format_url": format_url,
    }


@view_config(
    route_name="includes.edit-project-button",
    context=Project,
    renderer="includes/manage-project-button.html",
    uses_session=True,
    has_translations=True,
)
def edit_project_button(project, request):
    return {"project": project}


@view_config(
    context=Project,
    has_translations=True,
    renderer="includes/packaging/submit-malware-report.html",
    route_name="includes.submit_malware_report",
    uses_session=True,
)
def includes_submit_malware_observation(project, request):
    return {"project": project}


@view_config(
    context=Project,
    has_translations=True,
    permission=Permissions.SubmitMalwareObservation,
    renderer="packaging/submit-malware-observation.html",
    require_csrf=True,
    require_methods=False,
    route_name="packaging.project.submit_malware_observation",
    uses_session=True,
)
def submit_malware_observation(
    project,
    request,
    _form_class=SubmitMalwareObservationForm,
):
    """
    Allow Authenticated users to submit malware reports (observations) about a project.
    """
    form = _form_class(request.GET)

    if request.method == "POST":
        form = _form_class(request.POST)

        if form.validate():
            project.record_observation(
                request=request,
                kind=ObservationKind.IsMalware,
                actor=request.user,
                summary=form.summary.data,
                payload={
                    "inspector_url": form.inspector_link.data,
                    "origin": "web",
                    "summary": form.summary.data,
                },
            )
            request.session.flash(
                request._("Your report has been recorded. Thank you for your help."),
                queue="success",
            )
            return HTTPMovedPermanently(
                request.route_path("packaging.project", name=project.name)
            )

    return {"form": form, "project": project}
