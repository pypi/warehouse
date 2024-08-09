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
"""
Remove vestigial 2FA admin flag

Revision ID: fd06c4fe2f97
Revises: bb6943882aa9
Create Date: 2024-08-07 15:39:12.970946
"""


from alembic import op

revision = "fd06c4fe2f97"
down_revision = "bb6943882aa9"


def upgrade():
    op.execute("DELETE FROM admin_flags WHERE id = '2fa-required'")


def downgrade():
    op.execute(
        """
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            '2fa-required',
            'Require 2FA for all users',
            FALSE,
            FALSE
        )
    """
    )
