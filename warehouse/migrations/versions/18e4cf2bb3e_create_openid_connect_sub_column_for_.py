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
Create OpenID Connect 'sub' column for Google Users Migration

Revision ID: 18e4cf2bb3e
Revises: 116be7c87e1
Create Date: 2015-11-07 22:43:21.589230
"""

import sqlalchemy as sa

from alembic import op

revision = "18e4cf2bb3e"
down_revision = "116be7c87e1"


def upgrade():
    op.add_column("openids", sa.Column("sub", sa.Text()))

    op.create_index("openids_subkey", "openids", [sa.text("sub")], unique=True)


def downgrade():
    op.drop_index("openids_subkey", table_name="openids")
    op.drop_column("openids", "sub")
