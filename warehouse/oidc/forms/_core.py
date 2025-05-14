# SPDX-License-Identifier: Apache-2.0

import markupsafe
import structlog
import wtforms

from warehouse.i18n import localize as _
from warehouse.packaging.interfaces import (
    ProjectNameUnavailableExistingError,
    ProjectNameUnavailableInvalidError,
    ProjectNameUnavailableProhibitedError,
    ProjectNameUnavailableSimilarError,
    ProjectNameUnavailableStdlibError,
    ProjectNameUnavailableTypoSquattingError,
)
from warehouse.utils.project import PROJECT_NAME_RE

log = structlog.get_logger()


class PendingPublisherMixin:
    project_name = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message=_("Specify project name")),
            wtforms.validators.Regexp(
                PROJECT_NAME_RE, message=_("Invalid project name")
            ),
        ]
    )

    def validate_project_name(self, field):
        project_name = field.data

        try:
            self._check_project_name(project_name)
        except ProjectNameUnavailableInvalidError:
            raise wtforms.validators.ValidationError(_("Invalid project name"))
        except ProjectNameUnavailableExistingError as e:
            # If the user owns the existing project, the error message includes a
            # link to the project settings that the user can modify.
            if self._user in e.existing_project.owners:
                url_params = {name: value for name, value in self.data.items() if value}
                url_params["provider"] = {self.provider}
                url = self._route_url(
                    "manage.project.settings.publishing",
                    project_name=project_name,
                    _query=url_params,
                )

                # We mark the error message as safe, so that the HTML hyperlink is
                # not escaped by Jinja
                raise wtforms.validators.ValidationError(
                    markupsafe.Markup(
                        _(
                            "This project already exists: use the project's "
                            "publishing settings <a href='${url}'>here</a> to "
                            "create a Trusted Publisher for it.",
                            mapping={"url": url},
                        )
                    )
                )
            else:
                raise wtforms.validators.ValidationError(
                    _("This project already exists.")
                )

        except ProjectNameUnavailableProhibitedError:
            raise wtforms.validators.ValidationError(
                _("This project name isn't allowed")
            )
        except ProjectNameUnavailableSimilarError:
            raise wtforms.validators.ValidationError(
                _("This project name is too similar to an existing project")
            )
        except ProjectNameUnavailableStdlibError:
            raise wtforms.validators.ValidationError(
                _(
                    "This project name isn't allowed (conflict with the Python"
                    " standard library module name)"
                )
            )
        # TODO: Cover with testing and remove pragma
        except ProjectNameUnavailableTypoSquattingError as exc:  # pragma: no cover
            # TODO: raise with an appropriate message when we're ready to implement
            #  or combine with `ProjectNameUnavailableSimilarError`
            # TODO: This is an attempt at structlog, since `request.log` isn't in scope.
            #  We should be able to use `log` instead, but doesn't have the same output
            log.error(
                "Typo-squatting error raised but not handled in form validation",
                check_name=exc.check_name,
                existing_project_name=exc.existing_project_name,
            )
            pass

    @property
    def provider(self) -> str:  # pragma: no cover
        # Only concrete subclasses are constructed.
        raise NotImplementedError


class DeletePublisherForm(wtforms.Form):
    __params__ = ["publisher_id"]

    publisher_id = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message=_("Specify a publisher ID")),
            wtforms.validators.UUID(message=_("Publisher must be specified by ID")),
        ]
    )


class ConstrainEnvironmentForm(wtforms.Form):
    __params__ = ["constrained_publisher_id", "constrained_environment_name"]

    constrained_publisher_id = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message=_("Specify a publisher ID")),
            wtforms.validators.UUID(message=_("Publisher must be specified by ID")),
        ]
    )
    constrained_environment_name = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(message=_("Specify an environment name")),
        ]
    )
