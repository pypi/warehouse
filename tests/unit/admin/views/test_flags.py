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

from warehouse.admin.flags import AdminFlag
from warehouse.admin.views import flags as views

from ....common.db.admin import AdminFlagFactory


class TestGetFlags:

    def test_get_classifiers(self, db_request):
        # Clear out any existing flags added from migrations
        db_request.db.query(AdminFlag).delete()

        flag_a = AdminFlagFactory(id='flag-a')
        flag_b = AdminFlagFactory(id='flag-b')

        assert views.get_flags(db_request) == {
            'flags': [flag_a, flag_b],
        }


class TestEditFlag:

    @pytest.mark.parametrize(
        "description, enabled, post, expected_description, expected_enabled",
        [
            (
                # Nothing changed when enabled
                'old', True,
                {'id': 'foo-bar', 'description': 'old', 'enabled': 'on'},
                'old', True,
            ),
            (
                # Nothing changed when disabled
                'old', False,
                {'id': 'foo-bar', 'description': 'old'},
                'old', False,
            ),
            (
                # Enable flag
                'old', False,
                {'id': 'foo-bar', 'description': 'old', 'enabled': 'on'},
                'old', True,
            ),
            (
                # Disable flag
                'old', True,
                {'id': 'foo-bar', 'description': 'old'},
                'old', False,
            ),
            (
                # Change description when enabled
                'old', True,
                {'id': 'foo-bar', 'description': 'new', 'enabled': 'on'},
                'new', True,
            ),
            (
                # Change description when disabled
                'old', False,
                {'id': 'foo-bar', 'description': 'new'},
                'new', False,
            ),
        ]
    )
    def test_edit_flag(
            self, db_request, description, enabled, post, expected_description,
            expected_enabled):

        # Clear out any existing flags added from migrations
        db_request.db.query(AdminFlag).delete()

        flag = AdminFlagFactory(
            id='foo-bar',
            description=description,
            enabled=enabled,
        )

        db_request.POST = post
        db_request.route_path = lambda *a: '/the/redirect'
        db_request.flash = lambda *a: None

        views.edit_flag(db_request)

        db_request.db.flush()

        assert flag.enabled == expected_enabled
        assert flag.description == expected_description
