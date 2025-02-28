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
Add read-only AdminFlag

Revision ID: 6418f7d86a4b
Revises: 5dda74213989
Create Date: 2018-03-23 20:51:31.558587
"""

from alembic import op

revision = "6418f7d86a4b"
down_revision = "bf73e785eed9"


def upgrade():
    op.execute(
        """
        INSERT INTO warehouse_admin_flag(id, description, enabled, notify)
        VALUES (
            'read-only',
            'Read-only mode: Any write operations will have no effect',
            FALSE,
            TRUE
        )
    """
    )


def downgrade():
    op.execute("DELETE FROM warehouse_admin_flag WHERE id = 'read-only'")
