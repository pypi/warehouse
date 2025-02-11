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
Add a column to specify a project specific upload limit

Revision ID: 9177113533
Revises: 10cb17aea73
Create Date: 2015-09-04 21:06:59.950947
"""

import sqlalchemy as sa

from alembic import op

revision = "9177113533"
down_revision = "10cb17aea73"


def upgrade():
    op.add_column("packages", sa.Column("upload_limit", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("packages", "upload_limit")
