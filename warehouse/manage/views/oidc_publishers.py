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
    DeletePublisherForm,
    GitHubPublisherForm,
    GitLabPublisherForm,
    GooglePublisherForm,
)
from warehouse.oidc.forms._core import ConstrainEnvironmentForm
from warehouse.oidc.interfaces import TooManyOIDCRegistrations
from warehouse.oidc.models import (
    ActiveStatePublisher,
    GitHubPublisher,
    GitLabPublisher,
    GooglePublisher,
    OIDCPublisher,
)
from warehouse.oidc.view_mixins import OIDCPublisherViewMixin
from warehouse.packaging import Project


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
class ManageOIDCPublisherViews(OIDCPublisherViewMixin):
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
        self.prefilled_provider = None

    @property
    def default_response(self):
        return {
            "project": self.project,
            "github_publisher_form": self.github_publisher_form,
            "gitlab_publisher_form": self.gitlab_publisher_form,
            "google_publisher_form": self.google_publisher_form,
            "activestate_publisher_form": self.activestate_publisher_form,
            "disabled": self._disabled_publishers(),
            "prefilled_provider": self.prefilled_provider,
        }

    @view_config(request_method="GET")
    def manage_project_oidc_publishers(self):
        if self.request.flags.disallow_oidc():
            self._flash_oidc_disabled()

        return self.default_response

    @view_config(request_method="GET", request_param="provider")
    def manage_project_oidc_publishers_prefill(self):
        provider_mapping = {
            "github": self.github_publisher_form,
            "gitlab": self.gitlab_publisher_form,
            "google": self.google_publisher_form,
            "activestate": self.activestate_publisher_form,
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
            docs_url = self.request.user_docs_url(
                "/about/security-and-internals/",
                anchor="temporarily-disabled-features",
            )
            self.request.session.flash(
                (
                    "Trusted publishing is temporarily disabled. "
                    f"See {docs_url} for details."
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
                namespace_id=publisher.namespace_id,
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
        self.request.db.flush()  # ast-grep-ignore: db-flush -- constrained_publisher.id
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

    def _add_oidc_publisher(
        self,
        *,
        publisher_name,
        publisher_class,
        admin_flag,
        form_key,
        make_existence_filters,
        make_publisher,
    ):
        if self.request.flags.disallow_oidc(admin_flag):
            self._flash_oidc_disabled(publisher_name)
            return self.default_response

        metric_tags = [f"publisher:{publisher_name}"]
        self.metrics.increment("warehouse.oidc.add_publisher.attempt", tags=metric_tags)

        try:
            self._check_ratelimits()
        except TooManyOIDCRegistrations as exc:
            self.metrics.increment(
                "warehouse.oidc.add_publisher.ratelimited", tags=metric_tags
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
        form = response[form_key]

        if not form.validate():
            self.request.session.flash(
                self.request._("The trusted publisher could not be registered"),
                queue="error",
            )
            return response

        # Publishers are unique on their identifying claims, so we check for an
        # already registered one before creating.
        publisher = (
            self.request.db.query(publisher_class)
            .filter_by(**make_existence_filters(form))
            .one_or_none()
        )
        if publisher is None:
            publisher = make_publisher(form)
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

        self.metrics.increment("warehouse.oidc.add_publisher.ok", tags=metric_tags)

        return HTTPSeeOther(self.request.path)

    @view_config(
        request_method="POST",
        request_param=GitHubPublisherForm.__params__,
    )
    def add_github_oidc_publisher(self):
        return self._add_oidc_publisher(
            publisher_name="GitHub",
            publisher_class=GitHubPublisher,
            admin_flag=AdminFlagValue.DISALLOW_GITHUB_OIDC,
            form_key="github_publisher_form",
            make_existence_filters=lambda form: {
                "repository_name": form.repository.data,
                "repository_owner": form.normalized_owner,
                "workflow_filename": form.workflow_filename.data,
                "environment": form.normalized_environment,
            },
            make_publisher=lambda form: GitHubPublisher(
                repository_name=form.repository.data,
                repository_owner=form.normalized_owner,
                repository_owner_id=form.owner_id,
                workflow_filename=form.workflow_filename.data,
                environment=form.normalized_environment,
            ),
        )

    @view_config(
        request_method="POST",
        request_param=GitLabPublisherForm.__params__,
    )
    def add_gitlab_oidc_publisher(self):
        return self._add_oidc_publisher(
            publisher_name="GitLab",
            publisher_class=GitLabPublisher,
            admin_flag=AdminFlagValue.DISALLOW_GITLAB_OIDC,
            form_key="gitlab_publisher_form",
            make_existence_filters=lambda form: {
                "namespace": form.namespace.data,
                "project": form.project.data,
                "workflow_filepath": form.workflow_filepath.data,
                "environment": form.normalized_environment,
                "issuer_url": form.issuer_url.data,
            },
            make_publisher=lambda form: GitLabPublisher(
                namespace=form.namespace.data,
                project=form.project.data,
                workflow_filepath=form.workflow_filepath.data,
                environment=form.normalized_environment,
                issuer_url=form.issuer_url.data,
            ),
        )

    @view_config(
        request_method="POST",
        request_param=GooglePublisherForm.__params__,
    )
    def add_google_oidc_publisher(self):
        return self._add_oidc_publisher(
            publisher_name="Google",
            publisher_class=GooglePublisher,
            admin_flag=AdminFlagValue.DISALLOW_GOOGLE_OIDC,
            form_key="google_publisher_form",
            make_existence_filters=lambda form: {
                "email": form.email.data,
                "sub": form.sub.data,
            },
            make_publisher=lambda form: GooglePublisher(
                email=form.email.data,
                sub=form.sub.data,
            ),
        )

    @view_config(
        request_method="POST",
        request_param=ActiveStatePublisherForm.__params__,
    )
    def add_activestate_oidc_publisher(self):
        return self._add_oidc_publisher(
            publisher_name="ActiveState",
            publisher_class=ActiveStatePublisher,
            admin_flag=AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC,
            form_key="activestate_publisher_form",
            make_existence_filters=lambda form: {
                "organization": form.organization.data,
                "activestate_project_name": form.project.data,
                "actor_id": form.actor_id,
            },
            make_publisher=lambda form: ActiveStatePublisher(
                organization=form.organization.data,
                activestate_project_name=form.project.data,
                actor=form.actor.data,
                actor_id=form.actor_id,
            ),
        )

    @view_config(
        request_method="POST",
        request_param=DeletePublisherForm.__params__,
    )
    def delete_oidc_publisher(self):
        if self.request.flags.disallow_oidc():
            docs_url = self.request.user_docs_url(
                "/about/security-and-internals/",
                anchor="temporarily-disabled-features",
            )
            self.request.session.flash(
                (
                    "Trusted publishing is temporarily disabled. "
                    f"See {docs_url} for details."
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
