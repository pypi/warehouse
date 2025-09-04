# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from pyramid.exceptions import ConfigurationError
from pyramid.httpexceptions import HTTPSeeOther

from warehouse.organizations.models import OrganizationType
from warehouse.predicates import (
    ActiveOrganizationPredicate,
    DomainPredicate,
    HeadersPredicate,
    includeme,
)
from warehouse.subscriptions.models import StripeSubscriptionStatus

from ..common.db.organizations import (
    OrganizationFactory,
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

    def test_valid_value(self):
        predicate = DomainPredicate("upload.pypi.io", None)
        assert predicate(None, pretend.stub(domain="upload.pypi.io"))

    def test_invalid_value(self):
        predicate = DomainPredicate("upload.pyp.io", None)
        assert not predicate(None, pretend.stub(domain="pypi.io"))


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
    def test_valid_value(self, value):
        predicate = HeadersPredicate(value, None)
        assert predicate(None, pretend.stub(headers={"Foo": "a", "Bar": "baz"}))

    @pytest.mark.parametrize(
        "value",
        [["Foo", "Baz"], ["Foo", "Bar:foo"]],
    )
    def test_invalid_value(self, value):
        predicate = HeadersPredicate(value, None)
        assert not predicate(None, pretend.stub(headers={"Foo": "a", "Bar": "baz"}))


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

    def test_disable_organizations(self, db_request, organization):
        predicate = ActiveOrganizationPredicate(True, None)
        assert not predicate(organization, db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_inactive_organization(
        self,
        db_request,
        organization,
    ):
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations/"
        )

        organization.is_active = False
        predicate = ActiveOrganizationPredicate(True, None)
        with pytest.raises(HTTPSeeOther):
            predicate(organization, db_request)

        assert db_request.route_path.calls == [pretend.call("manage.organizations")]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_inactive_subscription(
        self,
        db_request,
        organization,
        inactive_subscription,
    ):
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations/"
        )

        predicate = ActiveOrganizationPredicate(True, None)
        with pytest.raises(HTTPSeeOther):
            predicate(organization, db_request)

        assert db_request.route_path.calls == [pretend.call("manage.organizations")]

    @pytest.mark.usefixtures("_enable_organizations")
    def test_active_subscription(
        self,
        db_request,
        organization,
        active_subscription,
    ):
        predicate = ActiveOrganizationPredicate(True, None)
        assert predicate(organization, db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_active_manual_activation(
        self,
        db_request,
        organization,
    ):
        import datetime

        from freezegun import freeze_time

        from ..common.db.organizations import OrganizationManualActivationFactory

        with freeze_time("2024-01-15"):
            # Create an active manual activation
            OrganizationManualActivationFactory(
                organization=organization,
                expires=datetime.date(2024, 12, 31),  # Future date
            )
            predicate = ActiveOrganizationPredicate(True, None)
            assert predicate(organization, db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_expired_manual_activation(
        self,
        db_request,
        organization,
    ):
        import datetime

        from freezegun import freeze_time

        from ..common.db.organizations import OrganizationManualActivationFactory

        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations/"
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

        assert db_request.route_path.calls == [pretend.call("manage.organizations")]


def test_includeme():
    config = pretend.stub(
        add_route_predicate=pretend.call_recorder(lambda name, pred: None),
        add_view_predicate=pretend.call_recorder(lambda name, pred: None),
    )
    includeme(config)

    assert config.add_route_predicate.calls == [pretend.call("domain", DomainPredicate)]

    assert config.add_view_predicate.calls == [
        pretend.call("require_headers", HeadersPredicate),
        pretend.call("require_active_organization", ActiveOrganizationPredicate),
    ]
