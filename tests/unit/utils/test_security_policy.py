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

from warehouse.accounts.interfaces import IUserService
from warehouse.utils import security_policy


@pytest.mark.parametrize(
    (
        "is_superuser",
        "is_moderator",
        "is_psf_staff",
        "password_out_of_date",
        "expected",
    ),
    [
        (False, False, False, False, []),
        (False, False, False, True, None),
        (
            True,
            False,
            False,
            False,
            [
                "group:admins",
                "group:moderators",
                "group:psf_staff",
                "group:with_admin_dashboard_access",
            ],
        ),
        (
            False,
            True,
            False,
            False,
            ["group:moderators", "group:with_admin_dashboard_access"],
        ),
        (
            True,
            True,
            False,
            False,
            [
                "group:admins",
                "group:moderators",
                "group:psf_staff",
                "group:with_admin_dashboard_access",
            ],
        ),
        (
            False,
            False,
            True,
            False,
            ["group:psf_staff", "group:with_admin_dashboard_access"],
        ),
        (
            False,
            True,
            True,
            False,
            [
                "group:moderators",
                "group:psf_staff",
                "group:with_admin_dashboard_access",
            ],
        ),
    ],
)
def test_principals_for_authenticated_user(
    pyramid_request,
    pyramid_services,
    is_superuser,
    is_moderator,
    is_psf_staff,
    password_out_of_date,
    expected,
):
    user = pretend.stub(
        id=1,
        is_superuser=is_superuser,
        is_moderator=is_moderator,
        is_psf_staff=is_psf_staff,
    )
    service = pretend.stub(
        get_password_timestamp=pretend.call_recorder(lambda userid: 0),
    )
    pyramid_services.register_service(service, IUserService, None)
    pyramid_request.session.password_outdated = lambda ts: password_out_of_date
    pyramid_request.session.invalidate = pretend.call_recorder(lambda: None)
    pyramid_request.session.flash = pretend.call_recorder(lambda msg, queue=None: None)

    assert (
        security_policy._principals_for_authenticated_user(user, pyramid_request)
        == expected
    )
    assert service.get_password_timestamp.calls == [pretend.call(1)]

    if password_out_of_date:
        assert pyramid_request.session.invalidate.calls == [pretend.call()]
        assert pyramid_request.session.flash.calls == [
            pretend.call("Session invalidated by password change", queue="error")
        ]
    else:
        assert pyramid_request.session.invalidate.calls == []
        assert pyramid_request.session.flash.calls == []
