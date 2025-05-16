# SPDX-License-Identifier: Apache-2.0

import enum

import pytest

from warehouse.admin.flags import AdminFlag, AdminFlagValue

from ...common.db.admin import AdminFlagFactory


class TestAdminFlagValues(enum.Enum):
    __test__ = False
    NOT_A_REAL_FLAG = "not-a-real-flag"
    THIS_FLAG_IS_ENABLED = "this-flag-is-enabled"


class TestAdminFlag:
    @pytest.mark.parametrize(
        ("disallow_oidc", "disallow_github_oidc", "oidc_enabled"),
        [
            (False, False, True),
            (True, False, False),
            (False, True, False),
            (True, True, False),
        ],
    )
    def test_disallow_oidc(
        self, db_request, disallow_oidc, disallow_github_oidc, oidc_enabled
    ):
        flag = db_request.db.get(AdminFlag, "disallow-oidc")
        flag.enabled = disallow_oidc

        flag = db_request.db.get(AdminFlag, "disallow-github-oidc")
        flag.enabled = disallow_github_oidc

        assert (
            not db_request.flags.disallow_oidc(AdminFlagValue.DISALLOW_GITHUB_OIDC)
            == oidc_enabled
        )
        assert db_request.flags.disallow_oidc() == disallow_oidc

    def test_default(self, db_request):
        assert not db_request.flags.enabled(TestAdminFlagValues.NOT_A_REAL_FLAG)

    def test_enabled(self, db_request):
        AdminFlagFactory(id="this-flag-is-enabled")

        assert db_request.flags.enabled(TestAdminFlagValues.THIS_FLAG_IS_ENABLED)
