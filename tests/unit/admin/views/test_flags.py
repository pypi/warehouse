# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.admin.flags import AdminFlag
from warehouse.admin.views import flags as views

from ....common.db.admin import AdminFlagFactory


class TestGetFlags:
    def test_get_classifiers(self, db_request):
        # Clear out any existing flags added from migrations
        db_request.db.query(AdminFlag).delete()

        flag_a = AdminFlagFactory(id="flag-a")
        flag_b = AdminFlagFactory(id="flag-b")

        assert views.get_flags(db_request) == {"flags": [flag_a, flag_b]}


class TestEditFlag:
    @pytest.mark.parametrize(
        ("description", "enabled", "post", "expected_description", "expected_enabled"),
        [
            (
                # Nothing changed when enabled
                "old",
                True,
                {"id": "foo-bar", "description": "old", "enabled": "on"},
                "old",
                True,
            ),
            (
                # Nothing changed when disabled
                "old",
                False,
                {"id": "foo-bar", "description": "old"},
                "old",
                False,
            ),
            (
                # Enable flag
                "old",
                False,
                {"id": "foo-bar", "description": "old", "enabled": "on"},
                "old",
                True,
            ),
            (
                # Disable flag
                "old",
                True,
                {"id": "foo-bar", "description": "old"},
                "old",
                False,
            ),
            (
                # Change description when enabled
                "old",
                True,
                {"id": "foo-bar", "description": "new", "enabled": "on"},
                "new",
                True,
            ),
            (
                # Change description when disabled
                "old",
                False,
                {"id": "foo-bar", "description": "new"},
                "new",
                False,
            ),
        ],
    )
    def test_edit_flag(
        self,
        db_request,
        description,
        enabled,
        post,
        expected_description,
        expected_enabled,
    ):
        # Clear out any existing flags added from migrations
        db_request.db.query(AdminFlag).delete()

        flag = AdminFlagFactory(id="foo-bar", description=description, enabled=enabled)

        db_request.POST = post
        db_request.route_path = lambda *a: "/the/redirect"
        db_request.flash = lambda *a: None

        views.edit_flag(db_request)

        db_request.db.flush()

        assert flag.enabled == expected_enabled
        assert flag.description == expected_description
