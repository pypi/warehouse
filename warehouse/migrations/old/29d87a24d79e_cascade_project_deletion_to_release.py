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
Cascade Project deletion to Release

Revision ID: 29d87a24d79e
Revises: c0682028c857
Create Date: 2018-03-09 22:37:21.343619
"""

from alembic import op

revision = "29d87a24d79e"
down_revision = "c0682028c857"


def upgrade():
    op.drop_constraint("releases_name_fkey", "releases", type_="foreignkey")
    op.create_foreign_key(
        "releases_name_fkey",
        "releases",
        "packages",
        ["name"],
        ["name"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint("releases_name_fkey", "releases", type_="foreignkey")
    op.create_foreign_key(
        "releases_name_fkey",
        "releases",
        "packages",
        ["name"],
        ["name"],
        onupdate="CASCADE",
    )
