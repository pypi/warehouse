# SPDX-License-Identifier: Apache-2.0

import pytest

from pyramid.httpexceptions import HTTPSeeOther

from warehouse.organizations.models import Organization
from warehouse.utils.organization import confirm_organization


def test_confirm(pyramid_request, mocker):
    organization = Organization(name="foobar", normalized_name="foobar")
    pyramid_request.POST = {"confirm_organization_name": "foobar"}
    route_path = mocker.patch.object(pyramid_request, "route_path", autospec=True)
    flash = mocker.spy(pyramid_request.session, "flash")

    confirm_organization(organization, pyramid_request, fail_route="fail_route")

    route_path.assert_not_called()
    flash.assert_not_called()


def test_confirm_no_input(pyramid_request, mocker):
    organization = Organization(name="foobar", normalized_name="foobar")
    pyramid_request.POST = {"confirm_organization_name": ""}
    route_path = mocker.patch.object(
        pyramid_request, "route_path", autospec=True, return_value="/the-redirect"
    )
    flash = mocker.spy(pyramid_request.session, "flash")

    with pytest.raises(HTTPSeeOther) as err:
        confirm_organization(organization, pyramid_request, fail_route="fail_route")
    assert err.value.location == "/the-redirect"

    route_path.assert_called_once_with("fail_route", organization_name="foobar")
    flash.assert_called_once_with("Confirm the request", queue="error")


def test_confirm_incorrect_input(pyramid_request, mocker):
    organization = Organization(name="foobar", normalized_name="foobar")
    pyramid_request.POST = {"confirm_organization_name": "bizbaz"}
    route_path = mocker.patch.object(
        pyramid_request, "route_path", autospec=True, return_value="/the-redirect"
    )
    flash = mocker.spy(pyramid_request.session, "flash")

    with pytest.raises(HTTPSeeOther) as err:
        confirm_organization(organization, pyramid_request, fail_route="fail_route")
    assert err.value.location == "/the-redirect"

    route_path.assert_called_once_with("fail_route", organization_name="foobar")
    flash.assert_called_once_with(
        "Could not delete organization - 'bizbaz' is not the same as 'foobar'",
        queue="error",
    )
