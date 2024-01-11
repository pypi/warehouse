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

import pretend
import pytest

from pyramid.exceptions import ConfigurationError
from pyramid.httpexceptions import HTTPSeeOther

from warehouse.organizations.models import OrganizationType
from warehouse.predicates import (
    ActiveOrganizationPredicate,
    APIPredicate,
    DomainPredicate,
    HeadersPredicate,
    _is_api_route,
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


class TestAPIPredicate:
    @pytest.mark.parametrize(
        ("value", "expected"), [(True, "is_api = True"), (False, "is_api = False")]
    )
    def test_text(self, value, expected):
        pred = APIPredicate(value, None)
        assert pred.text() == expected
        assert pred.phash() == expected

    @pytest.mark.parametrize("value", [True, False, None])
    def test_always_allows(self, value):
        pred = APIPredicate(value, None)
        assert pred(None, None)

    def test_request_no_matched_route(self):
        assert not _is_api_route(pretend.stub(matched_route=None))

    def test_request_matched_route_no_pred(self):
        request = pretend.stub(matched_route=pretend.stub(predicates=[]))
        assert not _is_api_route(request)

    def test_request_matched_route_no_api_pred(self):
        request = pretend.stub(matched_route=pretend.stub(predicates=[pretend.stub()]))
        assert not _is_api_route(request)

    @pytest.mark.parametrize(("value", "expected"), [(True, True), (False, False)])
    def test_request_matched_route_with_api_pred(self, value, expected):
        request = pretend.stub(
            matched_route=pretend.stub(predicates=[APIPredicate(value, None)])
        )
        assert _is_api_route(request) == expected


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

    def test_inactive_organization(
        self,
        db_request,
        organization,
        enable_organizations,
    ):
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations/"
        )

        organization.is_active = False
        predicate = ActiveOrganizationPredicate(True, None)
        with pytest.raises(HTTPSeeOther):
            predicate(organization, db_request)

        assert db_request.route_path.calls == [pretend.call("manage.organizations")]

    def test_inactive_subscription(
        self,
        db_request,
        organization,
        enable_organizations,
        inactive_subscription,
    ):
        db_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/manage/organizations/"
        )

        predicate = ActiveOrganizationPredicate(True, None)
        with pytest.raises(HTTPSeeOther):
            predicate(organization, db_request)

        assert db_request.route_path.calls == [pretend.call("manage.organizations")]

    def test_active_subscription(
        self, db_request, organization, enable_organizations, active_subscription
    ):
        predicate = ActiveOrganizationPredicate(True, None)
        assert predicate(organization, db_request)


def test_includeme():
    config = pretend.stub(
        add_request_method=pretend.call_recorder(lambda fn, name, reify: None),
        add_route_predicate=pretend.call_recorder(lambda name, pred: None),
        add_view_predicate=pretend.call_recorder(lambda name, pred: None),
    )
    includeme(config)

    assert config.add_request_method.calls == [
        pretend.call(_is_api_route, name="is_api", reify=True)
    ]

    assert config.add_route_predicate.calls == [
        pretend.call("domain", DomainPredicate),
        pretend.call("is_api", APIPredicate),
    ]

    assert config.add_view_predicate.calls == [
        pretend.call("require_headers", HeadersPredicate),
        pretend.call("require_active_organization", ActiveOrganizationPredicate),
    ]
