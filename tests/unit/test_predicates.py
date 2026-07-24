# SPDX-License-Identifier: Apache-2.0

import datetime
import types

import pytest

from freezegun import freeze_time
from pyramid.exceptions import ConfigurationError
from pyramid.httpexceptions import HTTPSeeOther

from warehouse.organizations.models import OrganizationType
from warehouse.predicates import (
    ActiveOrganizationPredicate,
    AuthMethodsPredicate,
    DomainPredicate,
    HeadersPredicate,
    auth_methods_for_route,
    includeme,
)
from warehouse.subscriptions.models import StripeSubscriptionStatus
from warehouse.utils.security_policy import AuthenticationMethod

from ..common.db.organizations import (
    OrganizationFactory,
    OrganizationManualActivationFactory,
    OrganizationStripeCustomerFactory,
    OrganizationStripeSubscriptionFactory,
)
from ..common.db.subscriptions import StripeSubscriptionFactory


class TestDomainPredicate:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(None, "domain = None"), ("pypi.io", "domain = {!r}".format("pypi.io"))],
    )
    def test_text(self, value, expected):
        predicate = DomainPredicate(value, None)
        assert predicate.text() == expected
        assert predicate.phash() == expected

    def test_when_not_set(self):
        predicate = DomainPredicate(None, None)
        assert predicate(None, None)

    def test_valid_value(self, pyramid_request):
        predicate = DomainPredicate("upload.pypi.io", None)
        pyramid_request.domain = "upload.pypi.io"
        assert predicate(None, pyramid_request)

    def test_invalid_value(self, pyramid_request):
        predicate = DomainPredicate("upload.pyp.io", None)
        pyramid_request.domain = "pypi.io"
        assert not predicate(None, pyramid_request)


class TestAuthMethodsPredicate:
    def test_text_and_phash(self):
        predicate = AuthMethodsPredicate(
            {AuthenticationMethod.SESSION, AuthenticationMethod.MACAROON}, None
        )
        assert predicate.text() == "auth_methods = ['macaroon', 'session']"
        assert predicate.phash() == predicate.text()

    def test_always_matches(self):
        predicate = AuthMethodsPredicate({AuthenticationMethod.SESSION}, None)
        assert predicate(None, None) is True

    def test_accepts_enum_values(self):
        predicate = AuthMethodsPredicate(
            {AuthenticationMethod.SESSION, AuthenticationMethod.MACAROON}, None
        )
        assert predicate.val == frozenset(
            {AuthenticationMethod.SESSION, AuthenticationMethod.MACAROON}
        )

    def test_accepts_string_values(self):
        predicate = AuthMethodsPredicate({"session", "macaroon"}, None)
        assert predicate.val == frozenset(
            {AuthenticationMethod.SESSION, AuthenticationMethod.MACAROON}
        )

    def test_rejects_unknown_values(self):
        with pytest.raises(ValueError, match="not a valid AuthenticationMethod"):
            AuthMethodsPredicate({"not-a-real-method"}, None)


class TestAuthMethodsForRoute:
    def test_returns_predicate_val(self):
        predicate = AuthMethodsPredicate({"macaroon"}, None)
        route = types.SimpleNamespace(predicates=[predicate])
        assert auth_methods_for_route(route) == frozenset(
            {AuthenticationMethod.MACAROON}
        )

    def test_returns_none_when_no_auth_methods_predicate(self):
        route = types.SimpleNamespace(predicates=[DomainPredicate("pypi.io", None)])
        assert auth_methods_for_route(route) is None


class TestHeadersPredicate:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (["Foo", "Bar"], "header Foo, header Bar"),
            (["Foo", "Bar:baz"], "header Foo, header Bar=baz"),
        ],
    )
    def test_text(self, value, expected):
        predicate = HeadersPredicate(value, None)
        assert predicate.text() == expected
        assert predicate.phash() == expected

    def test_when_empty(self):
        with pytest.raises(ConfigurationError):
            HeadersPredicate([], None)

    @pytest.mark.parametrize(
        "value",
        [["Foo", "Bar"], ["Foo", "Bar:baz"]],
    )
    def test_valid_value(self, value, pyramid_request):
        predicate = HeadersPredicate(value, None)
        pyramid_request.headers = {"Foo": "a", "Bar": "baz"}
        assert predicate(None, pyramid_request)

    @pytest.mark.parametrize(
        "value",
        [["Foo", "Baz"], ["Foo", "Bar:foo"]],
    )
    def test_invalid_value(self, value, pyramid_request):
        predicate = HeadersPredicate(value, None)
        pyramid_request.headers = {"Foo": "a", "Bar": "baz"}
        assert not predicate(None, pyramid_request)


class TestActiveOrganizationPredicate:
    @pytest.fixture
    def organization(self):
        organization = OrganizationFactory(
            orgtype=OrganizationType.Company,
        )
        OrganizationStripeCustomerFactory(
            organization=organization,
            stripe_customer_id="mock-customer-id",
        )
        return organization

    @pytest.fixture
    def active_subscription(self, organization):
        subscription = StripeSubscriptionFactory(
            stripe_customer_id=organization.customer.customer_id,
            status=StripeSubscriptionStatus.Active,
        )
        OrganizationStripeSubscriptionFactory(
            organization=organization,
            subscription=subscription,
        )
        return subscription

    @pytest.fixture
    def inactive_subscription(self, organization):
        subscription = StripeSubscriptionFactory(
            stripe_customer_id=organization.customer.customer_id,
            status=StripeSubscriptionStatus.PastDue,
        )
        OrganizationStripeSubscriptionFactory(
            organization=organization,
            subscription=subscription,
        )
        return subscription

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (True, "require_active_organization = True"),
            (False, "require_active_organization = False"),
        ],
    )
    def test_text(self, value, expected):
        predicate = ActiveOrganizationPredicate(value, None)
        assert predicate.text() == expected
        assert predicate.phash() == expected

    def test_disable_predicate(self, db_request, organization):
        predicate = ActiveOrganizationPredicate(False, None)
        assert predicate(organization, db_request)

    def test_inactive_organization(
        self,
        db_request,
        organization,
        mocker,
    ):
        route_path = mocker.patch.object(
            db_request, "route_path", return_value="/manage/organizations/"
        )

        organization.is_active = False
        predicate = ActiveOrganizationPredicate(True, None)
        with pytest.raises(HTTPSeeOther):
            predicate(organization, db_request)

        route_path.assert_called_once_with("manage.organizations")
        assert db_request.session.peek_flash("error") == [
            "This organization's billing is inactive. Activate billing to "
            "manage its projects, teams, and members."
        ]

    def test_inactive_subscription(
        self,
        db_request,
        organization,
        inactive_subscription,
        mocker,
    ):
        route_path = mocker.patch.object(
            db_request, "route_path", return_value="/manage/organizations/"
        )

        predicate = ActiveOrganizationPredicate(True, None)
        with pytest.raises(HTTPSeeOther):
            predicate(organization, db_request)

        route_path.assert_called_once_with("manage.organizations")

    def test_active_subscription(
        self,
        db_request,
        organization,
        active_subscription,
    ):
        predicate = ActiveOrganizationPredicate(True, None)
        assert predicate(organization, db_request)

    def test_active_manual_activation(
        self,
        db_request,
        organization,
    ):

        with freeze_time("2024-01-15"):
            # Create an active manual activation
            OrganizationManualActivationFactory(
                organization=organization,
                expires=datetime.date(2024, 12, 31),  # Future date
            )
            predicate = ActiveOrganizationPredicate(True, None)
            assert predicate(organization, db_request)

    def test_expired_manual_activation(
        self,
        db_request,
        organization,
        mocker,
    ):

        route_path = mocker.patch.object(
            db_request, "route_path", return_value="/manage/organizations/"
        )

        with freeze_time("2024-01-15"):
            # Create an expired manual activation
            OrganizationManualActivationFactory(
                organization=organization,
                expires=datetime.date(2023, 12, 31),  # Past date
            )
            predicate = ActiveOrganizationPredicate(True, None)
            with pytest.raises(HTTPSeeOther):
                predicate(organization, db_request)

        route_path.assert_called_once_with("manage.organizations")


def test_includeme(pyramid_config, mocker):
    add_route_predicate = mocker.patch.object(
        pyramid_config, "add_route_predicate", autospec=True
    )
    add_view_predicate = mocker.patch.object(
        pyramid_config, "add_view_predicate", autospec=True
    )
    includeme(pyramid_config)

    assert add_route_predicate.call_args_list == [
        mocker.call("domain", DomainPredicate),
        mocker.call("auth_methods", AuthMethodsPredicate),
    ]

    assert add_view_predicate.call_args_list == [
        mocker.call("require_headers", HeadersPredicate),
        mocker.call("require_active_organization", ActiveOrganizationPredicate),
    ]
