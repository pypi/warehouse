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

from pyramid.httpexceptions import HTTPNotFound

from warehouse.admin.views import organizations as views


class TestOrganizations:
    def test_detail(self):
        user = pretend.stub(
            username="example",
            name="Example",
            public_email="webmaster@example.com",
        )
        organization = pretend.stub(
            id=pretend.stub(),
            name="example",
            display_name="Example",
            orgtype=pretend.stub(name="Company"),
            link_url="https://www.example.com/",
            description=(
                "This company is for use in illustrative examples in documents "
                "You may use this company in literature without prior "
                "coordination or asking for permission."
            ),
            is_active=False,
            is_approved=None,
            users=[user],
        )
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: organization,
        )
        request = pretend.stub(
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_id": pretend.stub()},
        )

        assert views.detail(request) == {
            "user": user,
            "organization": organization,
        }

    def test_detail_not_found(self):
        organization_service = pretend.stub(
            get_organization=lambda *a, **kw: None,
        )
        request = pretend.stub(
            find_service=lambda *a, **kw: organization_service,
            matchdict={"organization_id": pretend.stub()},
        )

        with pytest.raises(HTTPNotFound):
            views.detail(request)

    def test_approve(self):
        organization = pretend.stub(id=pretend.stub())
        organization_detail_location = (f"/admin/organizations/{organization.id}/",)
        request = pretend.stub(
            matchdict={"organization_id": organization.id},
            route_path=lambda *a, **kw: organization_detail_location,
        )

        result = views.approve(request)

        assert result.status_code == 303
        assert result.location == organization_detail_location

    def test_decline(self):
        organization = pretend.stub(id=pretend.stub())
        organization_detail_location = (f"/admin/organizations/{organization.id}/",)
        request = pretend.stub(
            matchdict={"organization_id": organization.id},
            route_path=lambda *a, **kw: organization_detail_location,
        )

        result = views.decline(request)

        assert result.status_code == 303
        assert result.location == organization_detail_location
