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
Add Banner.dismissable

Revision ID: 095b491ebbec
Revises: 186f076eb60b
Create Date: 2023-11-16 17:04:43.250282
"""

import sqlalchemy as sa

from alembic import op

revision = "095b491ebbec"
down_revision = "186f076eb60b"


def upgrade():
    op.add_column("banners", sa.Column("dismissable", sa.Boolean(), nullable=False))


def downgrade():
    op.drop_column("banners", "dismissable")
