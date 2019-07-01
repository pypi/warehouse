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
add a column for sha256 digests

Revision ID: d8301a1bf519
Revises: 477bc785c999
Create Date: 2016-01-04 13:51:16.931595
"""

import citext
import sqlalchemy as sa

from alembic import op

revision = "d8301a1bf519"
down_revision = "477bc785c999"


def upgrade():
    op.add_column(
        "release_files", sa.Column("sha256_digest", citext.CIText(), nullable=True)
    )
    op.create_unique_constraint(None, "release_files", ["sha256_digest"])
    op.create_check_constraint(
        None, "release_files", "sha256_digest ~* '^[A-F0-9]{64}$'"
    )


def downgrade():
    op.drop_constraint(None, "release_files", type_="check")
    op.drop_constraint(None, "release_files", type_="unique")
    op.drop_column("release_files", "sha256_digest")
