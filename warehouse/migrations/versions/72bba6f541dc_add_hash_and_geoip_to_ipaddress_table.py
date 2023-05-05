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
add hash and geoip to IpAddress table

Revision ID: 72bba6f541dc
Revises: fd0479fed881
Create Date: 2023-05-05 16:37:01.130709
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "72bba6f541dc"
down_revision = "fd0479fed881"


def upgrade():
    op.add_column(
        "ip_addresses", sa.Column("hashed_ip_address", sa.Text(), nullable=True)
    )
    op.add_column(
        "ip_addresses",
        sa.Column("geoip_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_unique_constraint(None, "ip_addresses", ["hashed_ip_address"])


def downgrade():
    op.drop_constraint(None, "ip_addresses", type_="unique")
    op.drop_column("ip_addresses", "geoip_info")
    op.drop_column("ip_addresses", "hashed_ip_address")
