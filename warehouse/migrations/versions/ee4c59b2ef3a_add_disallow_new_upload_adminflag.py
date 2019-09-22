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
Add disallow-new-upload AdminFlag

Revision ID: ee4c59b2ef3a
Revises: 8650482fb903
Create Date: 2019-08-23 22:34:29.180163
"""

from alembic import op

revision = "ee4c59b2ef3a"
down_revision = "8650482fb903"


def upgrade():
    op.execute(
        """
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-new-upload',
            'Disallow ALL new uploads',
            FALSE,
            FALSE
        )
    """
    )


def downgrade():
    op.execute("DELETE FROM admin_flags WHERE id = 'disallow-new-upload'")
