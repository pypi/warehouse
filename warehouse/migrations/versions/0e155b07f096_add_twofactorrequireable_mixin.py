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
Add TwoFactorRequireable mixin

Revision ID: 0e155b07f096
Revises: 1b97443dea8a
Create Date: 2022-01-05 21:53:08.462640
"""

import sqlalchemy as sa

from alembic import op

revision = "0e155b07f096"
down_revision = "1b97443dea8a"


def upgrade():
    op.add_column(
        "projects",
        sa.Column(
            "owners_require_2fa",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "pypi_mandates_2fa",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("projects", "pypi_mandates_2fa")
    op.drop_column("projects", "owners_require_2fa")
