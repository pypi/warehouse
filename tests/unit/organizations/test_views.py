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

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound

from warehouse.organizations import views

from ...common.db.organizations import OrganizationFactory


class TestOrganizationProfile:
    def test_redirects_name(self, db_request):
        org = OrganizationFactory.create()

        if org.name.upper() != org.name:
            organization_name = org.name.upper()
        else:
            organization_name = org.name.lower()

        db_request.current_route_path = pretend.call_recorder(
            lambda organization: "/user/the-redirect/"
        )
        db_request.matchdict = {"organization": organization_name}

        result = views.profile(org, db_request)

        assert isinstance(result, HTTPMovedPermanently)
        assert result.headers["Location"] == "/user/the-redirect/"
        assert db_request.current_route_path.calls == [
            pretend.call(organization=org.name)
        ]

    def test_returns_organization(self, db_request):
        org = OrganizationFactory.create()
        assert views.profile(org, db_request) == {"organization": org}

    def test_4oh4_before_approval(self, db_request):
        org = OrganizationFactory.create(is_active=False)

        with pytest.raises(HTTPNotFound):
            views.profile(org, db_request)

        org.is_active = True
        assert views.profile(org, db_request) == {"organization": org}
