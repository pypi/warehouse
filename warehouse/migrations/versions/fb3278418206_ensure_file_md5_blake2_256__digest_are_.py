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
Ensure File.{md5,blake2_256}_digest are not nullable

Revision ID: fb3278418206
Revises: 0977b97fce94
Create Date: 2016-04-25 11:09:54.284023
"""

import citext
import sqlalchemy as sa

from alembic import op

revision = "fb3278418206"
down_revision = "0977b97fce94"


def upgrade():
    op.alter_column(
        "release_files",
        "blake2_256_digest",
        existing_type=citext.CIText(),
        nullable=False,
    )
    op.alter_column(
        "release_files", "md5_digest", existing_type=sa.TEXT(), nullable=False
    )


def downgrade():
    op.alter_column(
        "release_files", "md5_digest", existing_type=sa.TEXT(), nullable=True
    )
    op.alter_column(
        "release_files",
        "blake2_256_digest",
        existing_type=citext.CIText(),
        nullable=True,
    )
