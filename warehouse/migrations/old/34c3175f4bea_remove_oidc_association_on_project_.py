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
Remove OIDC Association on Project Delete

Revision ID: 34c3175f4bea
Revises: 1fdecaf73541
Create Date: 2024-04-09 21:38:26.340992
"""

from alembic import op

revision = "34c3175f4bea"
down_revision = "1fdecaf73541"


def upgrade():
    op.drop_constraint(
        "oidc_publisher_project_association_project_id_fkey",
        "oidc_publisher_project_association",
        type_="foreignkey",
    )
    op.create_foreign_key(
        None,
        "oidc_publisher_project_association",
        "projects",
        ["project_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(None, "oidc_publisher_project_association", type_="foreignkey")
    op.create_foreign_key(
        "oidc_publisher_project_association_project_id_fkey",
        "oidc_publisher_project_association",
        "projects",
        ["project_id"],
        ["id"],
    )
