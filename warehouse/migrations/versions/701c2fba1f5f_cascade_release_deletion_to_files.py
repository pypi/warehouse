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
Cascade Release deletion to Files

Revision ID: 701c2fba1f5f
Revises: b74a66a8f312
Create Date: 2018-03-09 23:06:05.382680
"""

from alembic import op

revision = "701c2fba1f5f"
down_revision = "b74a66a8f312"


def upgrade():
    op.execute(
        "ALTER TABLE release_files DROP CONSTRAINT IF EXISTS release_files_name_fkey"
    )
    op.create_foreign_key(
        "release_files_name_fkey",
        "release_files",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint("release_files_name_fkey", "release_files", type_="foreignkey")
    op.create_foreign_key(
        "release_files_name_fkey",
        "release_files",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
    )
