# SPDX-License-Identifier: Apache-2.0

from pyramid import predicates
from pyramid.exceptions import ConfigurationError
from pyramid.httpexceptions import HTTPSeeOther
from pyramid.util import is_same_domain

from warehouse.organizations.models import Organization, Team


class DomainPredicate:
    def __init__(self, val, config):
        self.val = val

    def text(self):
        return f"domain = {self.val!r}"

    phash = text

    def __call__(self, info, request):
        # Support running under the same instance for local development and for
        # test.pypi.io which will continue to host it's own uploader.
        if self.val is None:
            return True

        return is_same_domain(request.domain, self.val)


class HeadersPredicate:
    def __init__(self, val: list[str], config):
        if not val:
            raise ConfigurationError(
                "Excpected at least one value in headers predicate"
            )

        self.sub_predicates = [
            predicates.HeaderPredicate(subval, config) for subval in val
        ]

    def text(self):
        return ", ".join(sub.text() for sub in self.sub_predicates)

    phash = text

    def __call__(self, context, request):
        return all(sub(context, request) for sub in self.sub_predicates)


class ActiveOrganizationPredicate:
    def __init__(self, val, config):
        self.val = bool(val)

    def text(self):
        return f"require_active_organization = {self.val}"

    phash = text

    def __call__(self, context: Organization | Team, request):
        """Check that this organization is operational.

        Organization is operational (uses consolidated is_in_good_standing()
        method).

        """
        if self.val is False:
            return True

        organization = (
            context if isinstance(context, Organization) else context.organization
        )

        if organization.is_in_good_standing():
            return True
        else:
            raise HTTPSeeOther(request.route_path("manage.organizations"))


def includeme(config):
    config.add_route_predicate("domain", DomainPredicate)
    config.add_view_predicate("require_headers", HeadersPredicate)
    config.add_view_predicate(
        "require_active_organization", ActiveOrganizationPredicate
    )
