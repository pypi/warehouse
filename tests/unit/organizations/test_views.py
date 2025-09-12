# SPDX-License-Identifier: Apache-2.0

import pretend
import pytest

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound

from warehouse.organizations import views

from ...common.db.organizations import OrganizationFactory


class TestOrganizationProfile:
    def test_redirects_name(self, db_request):
        org = OrganizationFactory.create()

        db_request.current_route_path = pretend.call_recorder(
            lambda organization: "/user/the-redirect/"
        )
        db_request.matchdict = {"organization": org.name.swapcase()}

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
