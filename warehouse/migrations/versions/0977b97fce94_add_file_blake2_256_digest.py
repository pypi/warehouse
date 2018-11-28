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
Add File.blake2_256_digest

Revision ID: 0977b97fce94
Revises: f46672a776f1
Create Date: 2016-04-18 20:40:22.101245
"""

import citext
import sqlalchemy as sa

from alembic import op

revision = "0977b97fce94"
down_revision = "f46672a776f1"


def upgrade():
    op.add_column(
        "release_files", sa.Column("blake2_256_digest", citext.CIText(), nullable=True)
    )
    op.create_unique_constraint(None, "release_files", ["blake2_256_digest"])
    op.create_check_constraint(
        None, "release_files", "sha256_digest ~* '^[A-F0-9]{64}$'"
    )


def downgrade():
    raise RuntimeError("Cannot Go Backwards In Time.")
