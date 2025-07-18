# SPDX-License-Identifier: Apache-2.0

from typing import cast

from natsort import natsorted
from pypi_attestations import (
    Attestation,
    GitHubPublisher,
    GitLabPublisher,
    Publisher,
    TransparencyLogEntry,
)
from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.authnz import Permissions
from warehouse.cache.origin import origin_cache
from warehouse.observations.models import ObservationKind
from warehouse.packaging.forms import SubmitMalwareObservationForm
from warehouse.packaging.models import Description, File, Project, Release, Role


class PEP740AttestationViewer:

    def __init__(self, publisher: Publisher, attestation: Attestation):
        self.publisher = publisher
        self.attestation = attestation
        self.claims = self.attestation.certificate_claims

    def _format_url(self, base_url: str, reference: str) -> str:
        """Format a URL to create a permalink to a repository.

        Reference can either be a hash or a named revision.
        """
        match self.publisher.kind:
            case "GitHub":
                return f"{base_url}/tree/{reference}"
            case "GitLab":
                reference = reference.removeprefix("refs/heads/")
                return f"{base_url}/-/tree/{reference}"
            case _:
                # Best effort here
                return f"{base_url}/{reference}"

    # Statement properties
    @property
    def statement_type(self) -> str:
        """The type of the attestation statement."""
        return self.attestation.statement["_type"]

    @property
    def predicate_type(self) -> str:
        """The type of the predicate in the attestation statement."""
        return self.attestation.statement["predicateType"]

    @property
    def subject_name(self) -> str:
        """The name of the subject in the attestation."""
        return self.attestation.statement["subject"][0]["name"]

    @property
    def subject_digest(self) -> str:
        """The SHA256 digest of the subject."""
        return self.attestation.statement["subject"][0]["digest"]["sha256"]

    @property
    def transparency_entry(self) -> TransparencyLogEntry:
        """The first transparency log entry from the verification material."""
        return self.attestation.verification_material.transparency_entries[0]

    # Certificate properties
    @property
    def repository_url(self) -> str:
        """Source Repository URI."""
        return self.claims.get("1.3.6.1.4.1.57264.1.12", "")

    @property
    def workflow_filename(self) -> str:
        """The filename of the workflow configuration."""
        match self.publisher.kind:
            case "GitHub":
                return cast(GitHubPublisher, self.publisher).workflow
            case "GitLab":
                return cast(GitLabPublisher, self.publisher).workflow_filepath
            case _:
                return ""

    @property
    def workflow_url(self) -> str:
        """Build Config URI with permalink to the exact version used."""
        repo_url = self.repository_url
        workflow_url = self.claims.get("1.3.6.1.4.1.57264.1.18", "")
        workflow_file_path = workflow_url.split("@")[0].replace(repo_url + "/", "")
        return f"{repo_url}/blob/{self.build_digest}/{workflow_file_path}"

    @property
    def build_digest(self) -> str:
        """Build Config Digest."""
        return self.claims.get("1.3.6.1.4.1.57264.1.19", "")

    @property
    def issuer(self) -> str:
        """Issuer of the attestation."""
        return self.claims.get("1.3.6.1.4.1.57264.1.8", "")

    @property
    def environment(self) -> str:
        """Runner Environment."""
        return self.claims.get("1.3.6.1.4.1.57264.1.11", "")

    @property
    def source(self) -> str:
        """Source Repository URI."""
        return self.claims.get("1.3.6.1.4.1.57264.1.12", "")

    @property
    def source_digest(self) -> str:
        """Source Repository Digest."""
        return self.claims.get("1.3.6.1.4.1.57264.1.13", "")

    @property
    def source_reference(self) -> str:
        """Source Repository Reference."""
        return self.claims.get("1.3.6.1.4.1.57264.1.14", "")

    @property
    def owner(self) -> str:
        """Source Repository Owner URI."""
        return self.claims.get("1.3.6.1.4.1.57264.1.16", "")

    @property
    def trigger(self) -> str:
        """Build Trigger."""
        return self.claims.get("1.3.6.1.4.1.57264.1.20", "")

    @property
    def access(self) -> str:
        """Source Repository Visibility At Signing."""
        return self.claims.get("1.3.6.1.4.1.57264.1.22", "")

    @property
    def permalink_with_digest(self) -> str:
        """Construct a permalink using the source digest."""
        return self._format_url(self.source, self.source_digest)

    @property
    def permalink_with_reference(self) -> str:
        """Construct a permalink using the source reference."""
        return self._format_url(self.source, self.source_reference)


@view_config(
    route_name="packaging.project",
    context=Project,
    renderer="warehouse:templates/packaging/detail.html",
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


@view_config(
    route_name="packaging.release",
    context=Release,
    renderer="warehouse:templates/packaging/detail.html",
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

    license: str | None
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
        "PEP740AttestationViewer": PEP740AttestationViewer,
    }


@view_config(
    route_name="includes.edit-project-button",
    context=Project,
    renderer="warehouse:templates/includes/manage-project-button.html",
    uses_session=True,
    has_translations=True,
)
def edit_project_button(project, request):
    return {"project": project}


@view_config(
    context=Project,
    has_translations=True,
    permission=Permissions.SubmitMalwareObservation,
    renderer="warehouse:templates/packaging/submit-malware-observation.html",
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
