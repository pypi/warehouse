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
Admin Flag: 2fa-required

Revision ID: 0940ed80e40a
Revises: 4297620f7b41
Create Date: 2023-12-05 23:44:58.113194
"""

from alembic import op

revision = "0940ed80e40a"
down_revision = "4297620f7b41"


def upgrade():
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


def downgrade():
    op.execute("DELETE FROM admin_flags WHERE id = '2fa-required'")
