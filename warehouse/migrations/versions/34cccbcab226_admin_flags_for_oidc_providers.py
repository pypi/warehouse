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
admin flags for oidc providers

Revision ID: 34cccbcab226
Revises: 5dcbd2bc748f
Create Date: 2023-06-06 02:29:32.374813
"""

from alembic import op

revision = "34cccbcab226"
down_revision = "5dcbd2bc748f"


def upgrade():
    op.execute(
        """
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-github-oidc',
            'Disallow the GitHub OIDC provider',
            FALSE,
            FALSE
        )
        """
    )
    op.execute(
        """
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-google-oidc',
            'Disallow the Google OIDC provider',
            FALSE,
            FALSE
        )
        """
    )


def downgrade():
    op.execute("DELETE FROM admin_flags WHERE id = 'disallow-github-oidc'")
    op.execute("DELETE FROM admin_flags WHERE id = 'disallow-google-oidc'")
