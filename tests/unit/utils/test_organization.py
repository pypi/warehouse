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

from pretend import call, call_recorder, stub
from pyramid.httpexceptions import HTTPSeeOther

from warehouse.utils.organization import confirm_organization


def test_confirm():
    organization = stub(name="foobar", normalized_name="foobar")
    request = stub(
        POST={"confirm_organization_name": "foobar"},
        route_path=call_recorder(lambda *a, **kw: stub()),
        session=stub(flash=call_recorder(lambda *a, **kw: stub())),
    )

    confirm_organization(organization, request, fail_route="fail_route")

    assert request.route_path.calls == []
    assert request.session.flash.calls == []


def test_confirm_no_input():
    organization = stub(name="foobar", normalized_name="foobar")
    request = stub(
        POST={"confirm_organization_name": ""},
        route_path=call_recorder(lambda *a, **kw: "/the-redirect"),
        session=stub(flash=call_recorder(lambda *a, **kw: stub())),
    )

    with pytest.raises(HTTPSeeOther) as err:
        confirm_organization(organization, request, fail_route="fail_route")
    assert err.value.location == "/the-redirect"

    assert request.route_path.calls == [call("fail_route", organization_name="foobar")]
    assert request.session.flash.calls == [call("Confirm the request", queue="error")]


def test_confirm_incorrect_input():
    organization = stub(name="foobar", normalized_name="foobar")
    request = stub(
        POST={"confirm_organization_name": "bizbaz"},
        route_path=call_recorder(lambda *a, **kw: "/the-redirect"),
        session=stub(flash=call_recorder(lambda *a, **kw: stub())),
    )

    with pytest.raises(HTTPSeeOther) as err:
        confirm_organization(organization, request, fail_route="fail_route")
    assert err.value.location == "/the-redirect"

    assert request.route_path.calls == [call("fail_route", organization_name="foobar")]
    assert request.session.flash.calls == [
        call(
            "Could not delete organization - 'bizbaz' is not the same as 'foobar'",
            queue="error",
        )
    ]
