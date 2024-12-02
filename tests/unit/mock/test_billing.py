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

import pytest

from pyramid.httpexceptions import HTTPNotFound, HTTPSeeOther

from warehouse.mock import billing

from ...common.db.organizations import OrganizationFactory


class TestMockBillingViews:
    @pytest.fixture
    def organization(self):
        return OrganizationFactory.create()

    def test_disable_organizations(self, db_request, organization):
        db_request.organization_access = False
        with pytest.raises(HTTPNotFound):
            billing.MockBillingViews(organization, db_request)

    @pytest.mark.usefixtures("_enable_organizations")
    def test_mock_checkout_session(self, db_request, organization):
        view = billing.MockBillingViews(organization, db_request)
        result = view.mock_checkout_session()

        assert result == {"organization": organization}

    @pytest.mark.usefixtures("_enable_organizations")
    def test_mock_portal_session(self, db_request, organization):
        view = billing.MockBillingViews(organization, db_request)
        result = view.mock_portal_session()

        assert result == {"organization": organization}

    @pytest.mark.usefixtures("_enable_organizations")
    def test_mock_trigger_checkout_session_completed(
        self, db_request, organization, monkeypatch
    ):
        monkeypatch.setattr(
            db_request,
            "route_path",
            lambda *a, **kw: "/manage/organizations/",
        )
        monkeypatch.setattr(
            billing,
            "handle_billing_webhook_event",
            lambda *a, **kw: None,
        )

        view = billing.MockBillingViews(organization, db_request)
        result = view.mock_trigger_checkout_session_completed()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/manage/organizations/"
