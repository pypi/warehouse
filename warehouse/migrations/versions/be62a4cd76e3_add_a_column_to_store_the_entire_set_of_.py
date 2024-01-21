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
Add a column to store the entire set of serialized caveats

Revision ID: be62a4cd76e3
Revises: 812e14a4cddf
Create Date: 2024-01-20 16:28:31.573452
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "be62a4cd76e3"
down_revision = "812e14a4cddf"


def upgrade():
    op.add_column(
        "macaroons",
        sa.Column("caveats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Where our permissions_caveat is {"permission": "user"}, set our caveats to
    # [[3, str(user_id)]], which is a single RequestUser caveat where the user_id
    # is the attached user_id for this Macaroon.
    op.execute(
        """ UPDATE macaroons
            SET caveats = jsonb_build_array(jsonb_build_array(3, user_id::text))
            WHERE
                caveats IS NULL
                AND user_id IS NOT NULL
                AND permissions_caveat->>'permissions' = 'user'
        """
    )

    # Where our permissions_caveat is {"permission": [str, ...]}, set our caveats to
    # [[1, [str, ...]]], which is a single ProjectName caveat where the list of project
    # names is taken from the permissions_caveat.
    op.execute(
        """ UPDATE macaroons
            SET caveats = jsonb_build_array(
                jsonb_build_array(1, permissions_caveat->'permissions'->'projects')
            )
            WHERE
                caveats IS NULL
                AND jsonb_typeof(
                    permissions_caveat->'permissions'->'projects'
                ) = 'array'
        """
    )


def downgrade():
    op.drop_column("macaroons", "caveats")
