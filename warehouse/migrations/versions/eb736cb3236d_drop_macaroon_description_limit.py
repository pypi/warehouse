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
Drop Macaroon description limit

Revision ID: eb736cb3236d
Revises: cc06bd67a61b
Create Date: 2023-03-07 21:29:53.314390
"""

import sqlalchemy as sa

from alembic import op

revision = "eb736cb3236d"
down_revision = "cc06bd67a61b"


def upgrade():
    op.alter_column(
        "macaroons",
        "description",
        existing_type=sa.VARCHAR(length=100),
        type_=sa.String(),
        existing_nullable=False,
    )


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
