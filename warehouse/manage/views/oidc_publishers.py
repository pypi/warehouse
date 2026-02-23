# SPDX-License-Identifier: Apache-2.0

from pyramid.httpexceptions import HTTPSeeOther, HTTPTooManyRequests
from pyramid.view import view_config, view_defaults

from warehouse.admin.flags import AdminFlagValue
from warehouse.authnz import Permissions
from warehouse.email import (
    send_trusted_publisher_added_email,
    send_trusted_publisher_removed_email,
)
from warehouse.events.tags import EventTag
from warehouse.metrics import IMetricsService
from warehouse.oidc.forms import (
    ActiveStatePublisherForm,
    CircleCIPublisherForm,
    DeletePublisherForm,
    GitHubPublisherForm,
    GitLabPublisherForm,
    GooglePublisherForm,
)
from warehouse.oidc.forms._core import ConstrainEnvironmentForm
from warehouse.oidc.interfaces import TooManyOIDCRegistrations
from warehouse.oidc.models import (
    ActiveStatePublisher,
    CircleCIPublisher,
    GitHubPublisher,
    GitLabPublisher,
    GooglePublisher,
    OIDCPublisher,
)
from warehouse.packaging import Project
from warehouse.rate_limiting import IRateLimiter


@view_defaults(
    context=Project,
    route_name="manage.project.settings.publishing",
    renderer="warehouse:templates/manage/project/publishing.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission=Permissions.ProjectsWrite,
    has_translations=True,
    require_reauth=True,
    http_cache=0,
)
class ManageOIDCPublisherViews:
    def __init__(self, project, request):
        self.request = request
        self.project = project
        self.metrics = self.request.find_service(IMetricsService, context=None)
        self.github_publisher_form = GitHubPublisherForm(
            self.request.POST,
            api_token=self.request.registry.settings.get("github.token"),
        )
        _gl_issuers = GitLabPublisher.get_available_issuer_urls(
            organization=project.organization
        )
        self.gitlab_publisher_form = GitLabPublisherForm(
            self.request.POST,
            issuer_url_choices=_gl_issuers,
        )
        self.google_publisher_form = GooglePublisherForm(self.request.POST)
        self.activestate_publisher_form = ActiveStatePublisherForm(self.request.POST)
        self.circleci_publisher_form = CircleCIPublisherForm(self.request.POST)
        self.prefilled_provider = None

    @property
    def _ratelimiters(self):
        return {
            "user.oidc": self.request.find_service(
                IRateLimiter, name="user_oidc.publisher.register"
            ),
            "ip.oidc": self.request.find_service(
                IRateLimiter, name="ip_oidc.publisher.register"
            ),
        }

    def _hit_ratelimits(self):
        self._ratelimiters["user.oidc"].hit(self.request.user.id)
        self._ratelimiters["ip.oidc"].hit(self.request.remote_addr)

    def _check_ratelimits(self):
        if not self._ratelimiters["user.oidc"].test(self.request.user.id):
            raise TooManyOIDCRegistrations(
                resets_in=self._ratelimiters["user.oidc"].resets_in(
                    self.request.user.id
                )
            )

        if not self._ratelimiters["ip.oidc"].test(self.request.remote_addr):
            raise TooManyOIDCRegistrations(
                resets_in=self._ratelimiters["ip.oidc"].resets_in(
                    self.request.remote_addr
                )
            )

    @property
    def default_response(self):
        return {
            "project": self.project,
            "github_publisher_form": self.github_publisher_form,
            "gitlab_publisher_form": self.gitlab_publisher_form,
            "google_publisher_form": self.google_publisher_form,
            "activestate_publisher_form": self.activestate_publisher_form,
            "circleci_publisher_form": self.circleci_publisher_form,
            "disabled": {
                "GitHub": self.request.flags.disallow_oidc(
                    AdminFlagValue.DISALLOW_GITHUB_OIDC
                ),
                "GitLab": self.request.flags.disallow_oidc(
                    AdminFlagValue.DISALLOW_GITLAB_OIDC
                ),
                "Google": self.request.flags.disallow_oidc(
                    AdminFlagValue.DISALLOW_GOOGLE_OIDC
                ),
                "ActiveState": self.request.flags.disallow_oidc(
                    AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC
                ),
                "CircleCI": self.request.flags.disallow_oidc(
                    AdminFlagValue.DISALLOW_CIRCLECI_OIDC
                ),
            },
            "prefilled_provider": self.prefilled_provider,
        }

    @view_config(request_method="GET")
    def manage_project_oidc_publishers(self):
        if self.request.flags.disallow_oidc():
            self.request.session.flash(
                self.request._(
                    "Trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )

        return self.default_response

    @view_config(request_method="GET", request_param="provider")
    def manage_project_oidc_publishers_prefill(self):
        provider_mapping = {
            "github": self.github_publisher_form,
            "gitlab": self.gitlab_publisher_form,
            "google": self.google_publisher_form,
            "activestate": self.activestate_publisher_form,
            "circleci": self.circleci_publisher_form,
        }
        params = self.request.params
        provider = params.get("provider")
        provider = provider.lower() if provider else None
        if provider in provider_mapping:
            # The forms can be pre-filled by passing URL parameters. For example,
            # https://(...)//publishing?provider=github&owner=octo&repository=repo
            # will pre-fill the GitHub repository fields with `octo/repo`.
            provider_mapping[provider].process(params)
            self.prefilled_provider = provider

        return self.manage_project_oidc_publishers()

    @view_config(
        request_method="POST",
        request_param=ConstrainEnvironmentForm.__params__,
    )
    def constrain_environment(self):
        if self.request.flags.disallow_oidc():
            self.request.session.flash(
                (
                    "Trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
            return self.default_response

        self.metrics.increment("warehouse.oidc.constrain_publisher_environment.attempt")

        form = ConstrainEnvironmentForm(self.request.POST)

        if not form.validate():
            self.request.session.flash(
                self.request._("The trusted publisher could not be constrained"),
                queue="error",
            )
            return self.default_response

        publisher = self.request.db.get(
            OIDCPublisher, form.constrained_publisher_id.data
        )

        if publisher is None or publisher not in self.project.oidc_publishers:
            self.request.session.flash(
                "Invalid publisher for project",
                queue="error",
            )
            return self.default_response

        # First we add the new (constrained) trusted publisher
        if isinstance(publisher, GitHubPublisher):
            constrained_publisher = GitHubPublisher(
                repository_name=publisher.repository_name,
                repository_owner=publisher.repository_owner,
                repository_owner_id=publisher.repository_owner_id,
                workflow_filename=publisher.workflow_filename,
                environment=form.constrained_environment_name.data,
            )
        elif isinstance(publisher, GitLabPublisher):
            constrained_publisher = GitLabPublisher(
                namespace=publisher.namespace,
                project=publisher.project,
                workflow_filepath=publisher.workflow_filepath,
                environment=form.constrained_environment_name.data,
                issuer_url=publisher.issuer_url,
            )
        else:
            self.request.session.flash(
                "Can only constrain the environment for GitHub and GitLab publishers",
                queue="error",
            )
            return self.default_response

        # The user might have already manually created the new constrained publisher
        # before clicking the magic link to constrain the existing publisher.
        if constrained_publisher.exists(self.request.db):
            self.request.session.flash(
                self.request._(
                    f"{publisher} is already registered with {self.project.name}"
                ),
                queue="error",
            )
            return self.default_response

        if publisher.environment != "":
            self.request.session.flash(
                "Can only constrain the environment for publishers without an "
                "environment configured",
                queue="error",
            )
            return self.default_response

        self.request.db.add(constrained_publisher)
        self.request.db.flush()  # ensure constrained_publisher.id is available
        self.project.oidc_publishers.append(constrained_publisher)

        self.project.record_event(
            tag=EventTag.Project.OIDCPublisherAdded,
            request=self.request,
            additional={
                "publisher": constrained_publisher.publisher_name,
                "id": str(constrained_publisher.id),
                "specifier": str(constrained_publisher),
                "url": constrained_publisher.publisher_url(),
                "submitted_by": self.request.user.username,
                "reified_from_pending_publisher": False,
                "constrained_from_existing_publisher": True,
            },
        )

        # Then, we remove the old trusted publisher from the project
        # and, if there are no projects left associated with the publisher,
        # we delete it entirely.
        self.project.oidc_publishers.remove(publisher)
        if len(publisher.projects) == 0:
            self.request.db.delete(publisher)

        self.project.record_event(
            tag=EventTag.Project.OIDCPublisherRemoved,
            request=self.request,
            additional={
                "publisher": publisher.publisher_name,
                "id": str(publisher.id),
                "specifier": str(publisher),
                "url": publisher.publisher_url(),
                "submitted_by": self.request.user.username,
            },
        )

        self.request.session.flash(
            self.request._(
                f"Trusted publisher for project {self.project.name!r} has been "
                f"constrained to environment {constrained_publisher.environment!r}"
            ),
            queue="success",
        )

        return HTTPSeeOther(self.request.path)

    @view_config(
        request_method="POST",
        request_param=GitHubPublisherForm.__params__,
    )
    def add_github_oidc_publisher(self):
        if self.request.flags.disallow_oidc(AdminFlagValue.DISALLOW_GITHUB_OIDC):
            self.request.session.flash(
                self.request._(
                    "GitHub-based trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
            return self.default_response

        self.metrics.increment(
            "warehouse.oidc.add_publisher.attempt", tags=["publisher:GitHub"]
        )

        try:
            self._check_ratelimits()
        except TooManyOIDCRegistrations as exc:
            self.metrics.increment(
                "warehouse.oidc.add_publisher.ratelimited", tags=["publisher:GitHub"]
            )
            return HTTPTooManyRequests(
                self.request._(
                    "There have been too many attempted trusted publisher "
                    "registrations. Try again later."
                ),
                retry_after=exc.resets_in.total_seconds(),
            )

        self._hit_ratelimits()

        response = self.default_response
        form = response["github_publisher_form"]

        if not form.validate():
            self.request.session.flash(
                self.request._("The trusted publisher could not be registered"),
                queue="error",
            )
            return response

        # GitHub OIDC publishers are unique on the tuple of
        # (repository_name, repository_owner, workflow_filename, environment),
        # so we check for an already registered one before creating.
        publisher = (
            self.request.db.query(GitHubPublisher)
            .filter(
                GitHubPublisher.repository_name == form.repository.data,
                GitHubPublisher.repository_owner == form.normalized_owner,
                GitHubPublisher.workflow_filename == form.workflow_filename.data,
                GitHubPublisher.environment == form.normalized_environment,
            )
            .one_or_none()
        )
        if publisher is None:
            publisher = GitHubPublisher(
                repository_name=form.repository.data,
                repository_owner=form.normalized_owner,
                repository_owner_id=form.owner_id,
                workflow_filename=form.workflow_filename.data,
                environment=form.normalized_environment,
            )

            self.request.db.add(publisher)

        # Each project has a unique set of OIDC publishers; the same
        # publisher can't be registered to the project more than once.
        if publisher in self.project.oidc_publishers:
            self.request.session.flash(
                self.request._(
                    f"{publisher} is already registered with {self.project.name}"
                ),
                queue="error",
            )
            return response

        for user in self.project.users:
            send_trusted_publisher_added_email(
                self.request,
                user,
                project_name=self.project.name,
                publisher=publisher,
            )

        self.project.oidc_publishers.append(publisher)

        self.project.record_event(
            tag=EventTag.Project.OIDCPublisherAdded,
            request=self.request,
            additional={
                "publisher": publisher.publisher_name,
                "id": str(publisher.id),
                "specifier": str(publisher),
                "url": publisher.publisher_url(),
                "submitted_by": self.request.user.username,
                "reified_from_pending_publisher": False,
                "constrained_from_existing_publisher": False,
            },
        )

        self.request.session.flash(
            f"Added {publisher} in {publisher.publisher_url()} to {self.project.name}",
            queue="success",
        )

        self.metrics.increment(
            "warehouse.oidc.add_publisher.ok", tags=["publisher:GitHub"]
        )

        return HTTPSeeOther(self.request.path)

    @view_config(
        request_method="POST",
        request_param=GitLabPublisherForm.__params__,
    )
    def add_gitlab_oidc_publisher(self):
        if self.request.flags.disallow_oidc(AdminFlagValue.DISALLOW_GITLAB_OIDC):
            self.request.session.flash(
                self.request._(
                    "GitLab-based trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
            return self.default_response

        self.metrics.increment(
            "warehouse.oidc.add_publisher.attempt", tags=["publisher:GitLab"]
        )

        try:
            self._check_ratelimits()
        except TooManyOIDCRegistrations as exc:
            self.metrics.increment(
                "warehouse.oidc.add_publisher.ratelimited", tags=["publisher:GitLab"]
            )
            return HTTPTooManyRequests(
                self.request._(
                    "There have been too many attempted trusted publisher "
                    "registrations. Try again later."
                ),
                retry_after=exc.resets_in.total_seconds(),
            )

        self._hit_ratelimits()

        response = self.default_response
        form = response["gitlab_publisher_form"]

        if not form.validate():
            self.request.session.flash(
                self.request._("The trusted publisher could not be registered"),
                queue="error",
            )
            return response

        # GitLab OIDC publishers are unique on the tuple of
        # (namespace, project, workflow_filepath, environment),
        # so we check for an already registered one before creating.
        publisher = (
            self.request.db.query(GitLabPublisher)
            .filter(
                GitLabPublisher.namespace == form.namespace.data,
                GitLabPublisher.project == form.project.data,
                GitLabPublisher.workflow_filepath == form.workflow_filepath.data,
                GitLabPublisher.environment == form.normalized_environment,
                GitLabPublisher.issuer_url == form.issuer_url.data,
            )
            .one_or_none()
        )
        if publisher is None:
            publisher = GitLabPublisher(
                namespace=form.namespace.data,
                project=form.project.data,
                workflow_filepath=form.workflow_filepath.data,
                environment=form.normalized_environment,
                issuer_url=form.issuer_url.data,
            )

            self.request.db.add(publisher)

        # Each project has a unique set of OIDC publishers; the same
        # publisher can't be registered to the project more than once.
        if publisher in self.project.oidc_publishers:
            self.request.session.flash(
                self.request._(
                    f"{publisher} is already registered with {self.project.name}"
                ),
                queue="error",
            )
            return response

        for user in self.project.users:
            send_trusted_publisher_added_email(
                self.request,
                user,
                project_name=self.project.name,
                publisher=publisher,
            )

        self.project.oidc_publishers.append(publisher)

        self.project.record_event(
            tag=EventTag.Project.OIDCPublisherAdded,
            request=self.request,
            additional={
                "publisher": publisher.publisher_name,
                "id": str(publisher.id),
                "specifier": str(publisher),
                "url": publisher.publisher_url(),
                "submitted_by": self.request.user.username,
                "reified_from_pending_publisher": False,
                "constrained_from_existing_publisher": False,
            },
        )

        self.request.session.flash(
            f"Added {publisher} in {publisher.publisher_url()} to {self.project.name}",
            queue="success",
        )

        self.metrics.increment(
            "warehouse.oidc.add_publisher.ok", tags=["publisher:GitLab"]
        )

        return HTTPSeeOther(self.request.path)

    @view_config(
        request_method="POST",
        request_param=GooglePublisherForm.__params__,
    )
    def add_google_oidc_publisher(self):
        if self.request.flags.disallow_oidc(AdminFlagValue.DISALLOW_GOOGLE_OIDC):
            self.request.session.flash(
                self.request._(
                    "Google-based trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
            return self.default_response

        self.metrics.increment(
            "warehouse.oidc.add_publisher.attempt", tags=["publisher:Google"]
        )

        try:
            self._check_ratelimits()
        except TooManyOIDCRegistrations as exc:
            self.metrics.increment(
                "warehouse.oidc.add_publisher.ratelimited", tags=["publisher:Google"]
            )
            return HTTPTooManyRequests(
                self.request._(
                    "There have been too many attempted trusted publisher "
                    "registrations. Try again later."
                ),
                retry_after=exc.resets_in.total_seconds(),
            )

        self._hit_ratelimits()

        response = self.default_response
        form = response["google_publisher_form"]

        if not form.validate():
            self.request.session.flash(
                self.request._("The trusted publisher could not be registered"),
                queue="error",
            )
            return response

        # Google OIDC publishers are unique on the tuple of (email, sub), so we
        # check for an already registered one before creating.
        publisher = (
            self.request.db.query(GooglePublisher)
            .filter(
                GooglePublisher.email == form.email.data,
                GooglePublisher.sub == form.sub.data,
            )
            .one_or_none()
        )
        if publisher is None:
            publisher = GooglePublisher(
                email=form.email.data,
                sub=form.sub.data,
            )

            self.request.db.add(publisher)

        # Each project has a unique set of OIDC publishers; the same
        # publisher can't be registered to the project more than once.
        if publisher in self.project.oidc_publishers:
            self.request.session.flash(
                self.request._(
                    f"{publisher} is already registered with {self.project.name}"
                ),
                queue="error",
            )
            return response

        for user in self.project.users:
            send_trusted_publisher_added_email(
                self.request,
                user,
                project_name=self.project.name,
                publisher=publisher,
            )

        self.project.oidc_publishers.append(publisher)

        self.project.record_event(
            tag=EventTag.Project.OIDCPublisherAdded,
            request=self.request,
            additional={
                "publisher": publisher.publisher_name,
                "id": str(publisher.id),
                "specifier": str(publisher),
                "url": publisher.publisher_url(),
                "submitted_by": self.request.user.username,
                "reified_from_pending_publisher": False,
                "constrained_from_existing_publisher": False,
            },
        )

        self.request.session.flash(
            f"Added {publisher} "
            + (f"in {publisher.publisher_url()}" if publisher.publisher_url() else "")
            + f" to {self.project.name}",
            queue="success",
        )

        self.metrics.increment(
            "warehouse.oidc.add_publisher.ok", tags=["publisher:Google"]
        )

        return HTTPSeeOther(self.request.path)

    @view_config(
        request_method="POST",
        request_param=ActiveStatePublisherForm.__params__,
    )
    def add_activestate_oidc_publisher(self):
        if self.request.flags.disallow_oidc(AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC):
            self.request.session.flash(
                self.request._(
                    "ActiveState-based trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
            return self.default_response

        self.metrics.increment(
            "warehouse.oidc.add_publisher.attempt", tags=["publisher:ActiveState"]
        )

        try:
            self._check_ratelimits()
        except TooManyOIDCRegistrations as exc:
            self.metrics.increment(
                "warehouse.oidc.add_publisher.ratelimited",
                tags=["publisher:ActiveState"],
            )
            return HTTPTooManyRequests(
                self.request._(
                    "There have been too many attempted trusted publisher "
                    "registrations. Try again later."
                ),
                retry_after=exc.resets_in.total_seconds(),
            )

        self._hit_ratelimits()

        response = self.default_response
        form = response["activestate_publisher_form"]

        if not form.validate():
            self.request.session.flash(
                self.request._("The trusted publisher could not be registered"),
                queue="error",
            )
            return response

        # Check for an already registered publisher before creating.
        publisher = (
            self.request.db.query(ActiveStatePublisher)
            .filter(
                ActiveStatePublisher.organization == form.organization.data,
                ActiveStatePublisher.activestate_project_name == form.project.data,
                ActiveStatePublisher.actor_id == form.actor_id,
            )
            .one_or_none()
        )
        if publisher is None:
            publisher = ActiveStatePublisher(
                organization=form.organization.data,
                activestate_project_name=form.project.data,
                actor=form.actor.data,
                actor_id=form.actor_id,
            )

            self.request.db.add(publisher)

        # Each project has a unique set of OIDC publishers; the same
        # publisher can't be registered to the project more than once.
        if publisher in self.project.oidc_publishers:
            self.request.session.flash(
                self.request._(
                    f"{publisher} is already registered with {self.project.name}"
                ),
                queue="error",
            )
            return response

        for user in self.project.users:
            send_trusted_publisher_added_email(
                self.request,
                user,
                project_name=self.project.name,
                publisher=publisher,
            )

        self.project.oidc_publishers.append(publisher)

        self.project.record_event(
            tag=EventTag.Project.OIDCPublisherAdded,
            request=self.request,
            additional={
                "publisher": publisher.publisher_name,
                "id": str(publisher.id),
                "specifier": str(publisher),
                "url": publisher.publisher_url(),
                "submitted_by": self.request.user.username,
                "reified_from_pending_publisher": False,
                "constrained_from_existing_publisher": False,
            },
        )

        self.request.session.flash(
            f"Added {publisher} in {publisher.publisher_url()} to {self.project.name}",
            queue="success",
        )

        self.metrics.increment(
            "warehouse.oidc.add_publisher.ok", tags=["publisher:ActiveState"]
        )

        return HTTPSeeOther(self.request.path)

    @view_config(
        request_method="POST",
        request_param=CircleCIPublisherForm.__params__,
    )
    def add_circleci_oidc_publisher(self):
        if self.request.flags.disallow_oidc(AdminFlagValue.DISALLOW_CIRCLECI_OIDC):
            self.request.session.flash(
                self.request._(
                    "CircleCI-based trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
            return self.default_response

        self.metrics.increment(
            "warehouse.oidc.add_publisher.attempt", tags=["publisher:CircleCI"]
        )

        try:
            self._check_ratelimits()
        except TooManyOIDCRegistrations as exc:
            self.metrics.increment(
                "warehouse.oidc.add_publisher.ratelimited",
                tags=["publisher:CircleCI"],
            )
            return HTTPTooManyRequests(
                self.request._(
                    "There have been too many attempted trusted publisher "
                    "registrations. Try again later."
                ),
                retry_after=exc.resets_in.total_seconds(),
            )

        self._hit_ratelimits()

        response = self.default_response
        form = response["circleci_publisher_form"]

        if not form.validate():
            self.request.session.flash(
                self.request._("The trusted publisher could not be registered"),
                queue="error",
            )
            return response

        # CircleCI OIDC publishers are unique on the tuple of
        # (circleci_org_id, circleci_project_id, pipeline_definition_id, context_id,
        # vcs_ref, vcs_origin), so we check for an already registered one before
        # creating.
        publisher = (
            self.request.db.query(CircleCIPublisher)
            .filter(
                CircleCIPublisher.circleci_org_id == form.circleci_org_id.data,
                CircleCIPublisher.circleci_project_id == form.circleci_project_id.data,
                CircleCIPublisher.pipeline_definition_id
                == form.pipeline_definition_id.data,
                CircleCIPublisher.context_id == form.normalized_context_id,
                CircleCIPublisher.vcs_ref == form.normalized_vcs_ref,
                CircleCIPublisher.vcs_origin == form.normalized_vcs_origin,
            )
            .one_or_none()
        )
        if publisher is None:
            publisher = CircleCIPublisher(
                circleci_org_id=form.circleci_org_id.data,
                circleci_project_id=form.circleci_project_id.data,
                pipeline_definition_id=form.pipeline_definition_id.data,
                context_id=form.normalized_context_id,
                vcs_ref=form.normalized_vcs_ref,
                vcs_origin=form.normalized_vcs_origin,
            )

            self.request.db.add(publisher)

        # Each project has a unique set of OIDC publishers; the same
        # publisher can't be registered to the project more than once.
        if publisher in self.project.oidc_publishers:
            self.request.session.flash(
                self.request._(
                    f"{publisher} is already registered with {self.project.name}"
                ),
                queue="error",
            )
            return response

        for user in self.project.users:
            send_trusted_publisher_added_email(
                self.request,
                user,
                project_name=self.project.name,
                publisher=publisher,
            )

        self.project.oidc_publishers.append(publisher)

        self.project.record_event(
            tag=EventTag.Project.OIDCPublisherAdded,
            request=self.request,
            additional={
                "publisher": publisher.publisher_name,
                "id": str(publisher.id),
                "specifier": str(publisher),
                "url": publisher.publisher_url(),
                "submitted_by": self.request.user.username,
                "reified_from_pending_publisher": False,
                "constrained_from_existing_publisher": False,
            },
        )

        self.request.session.flash(
            f"Added {publisher} "
            + (f"in {publisher.publisher_url()}" if publisher.publisher_url() else "")
            + f" to {self.project.name}",
            queue="success",
        )

        self.metrics.increment(
            "warehouse.oidc.add_publisher.ok", tags=["publisher:CircleCI"]
        )

        return HTTPSeeOther(self.request.path)

    @view_config(
        request_method="POST",
        request_param=DeletePublisherForm.__params__,
    )
    def delete_oidc_publisher(self):
        if self.request.flags.disallow_oidc():
            self.request.session.flash(
                (
                    "Trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
            return self.default_response

        self.metrics.increment("warehouse.oidc.delete_publisher.attempt")

        form = DeletePublisherForm(self.request.POST)

        if form.validate():
            publisher = self.request.db.get(OIDCPublisher, form.publisher_id.data)

            # publisher will be `None` here if someone manually futzes with the form.
            if publisher is None or publisher not in self.project.oidc_publishers:
                self.request.session.flash(
                    "Invalid publisher for project",
                    queue="error",
                )
                return self.default_response

            for user in self.project.users:
                send_trusted_publisher_removed_email(
                    self.request,
                    user,
                    project_name=self.project.name,
                    publisher=publisher,
                )

            self.project.record_event(
                tag=EventTag.Project.OIDCPublisherRemoved,
                request=self.request,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": str(publisher.id),
                    "specifier": str(publisher),
                    "url": publisher.publisher_url(),
                    "submitted_by": self.request.user.username,
                },
            )

            # We remove this publisher from the project's list of publishers
            # and, if there are no projects left associated with the publisher,
            # we delete it entirely.
            self.project.oidc_publishers.remove(publisher)
            if len(publisher.projects) == 0:
                self.request.db.delete(publisher)

            self.request.session.flash(
                self.request._(
                    f"Removed trusted publisher for project {self.project.name!r}"
                ),
                queue="success",
            )

            self.metrics.increment(
                "warehouse.oidc.delete_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            )

            return HTTPSeeOther(self.request.path)

        return self.default_response
