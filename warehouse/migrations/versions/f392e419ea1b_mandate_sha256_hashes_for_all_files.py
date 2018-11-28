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
mandate sha256 hashes for all files

Revision ID: f392e419ea1b
Revises: d8301a1bf519
Create Date: 2016-01-04 16:20:50.428491
"""

from alembic import op

revision = "f392e419ea1b"
down_revision = "d8301a1bf519"


def upgrade():
    op.alter_column("release_files", "sha256_digest", nullable=False)


def downgrade():
    op.alter_column("release_files", "sha256_digest", nullable=True)
