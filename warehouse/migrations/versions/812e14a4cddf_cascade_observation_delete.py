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
cascade observation delete

Revision ID: 812e14a4cddf
Revises: a073e7979805
Create Date: 2024-01-18 18:46:58.482270
"""

from alembic import op

revision = "812e14a4cddf"
down_revision = "9a0ed2044b53"


def upgrade():
    op.drop_constraint(
        "project_observations_related_id_fkey",
        "project_observations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        None,
        "project_observations",
        "projects",
        ["related_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "release_observations_related_id_fkey",
        "release_observations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        None,
        "release_observations",
        "releases",
        ["related_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(
        "release_observations_related_id_fkey",
        "release_observations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "release_observations_related_id_fkey",
        "release_observations",
        "releases",
        ["related_id"],
        ["id"],
    )
    op.drop_constraint(
        "project_observations_related_id_fkey",
        "project_observations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "project_observations_related_id_fkey",
        "project_observations",
        "projects",
        ["related_id"],
        ["id"],
    )
