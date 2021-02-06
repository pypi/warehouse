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
Change upload_limit to BigInteger

Revision ID: 38b288a33869
Revises: 99a201142761
Create Date: 2021-02-06 17:03:47.792858
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "38b288a33869"
down_revision = "99a201142761"


def upgrade():
    op.alter_column(
        "projects",
        "upload_limit",
        existing_type=sa.INTEGER(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "projects",
        "upload_limit",
        existing_type=sa.BigInteger(),
        type_=sa.INTEGER(),
        existing_nullable=True,
    )
