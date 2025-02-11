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
Cascade Release deletion to Release Classifiers

Revision ID: b74a66a8f312
Revises: 29d87a24d79e
Create Date: 2018-03-09 22:55:38.166123
"""

from alembic import op

revision = "b74a66a8f312"
down_revision = "29d87a24d79e"


def upgrade():
    op.execute(
        "ALTER TABLE release_classifiers "
        "DROP CONSTRAINT IF EXISTS release_classifiers_name_fkey"
    )
    op.create_foreign_key(
        "release_classifiers_name_fkey",
        "release_classifiers",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(
        "release_classifiers_name_fkey", "release_classifiers", type_="foreignkey"
    )
    op.create_foreign_key(
        "release_classifiers_name_fkey",
        "release_classifiers",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
    )
