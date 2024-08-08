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
create verified field for ReleaseUrl

Revision ID: 26455e3712a2
Revises: b14df478c48f
Create Date: 2024-04-30 18:40:17.149050
"""

import sqlalchemy as sa

from alembic import op

revision = "26455e3712a2"
down_revision = "b14df478c48f"


def upgrade():
    op.add_column(
        "release_urls",
        sa.Column(
            "verified", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("release_urls", "verified")
