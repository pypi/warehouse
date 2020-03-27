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
enforce uniqueness of user_id, project_id on roles

Revision ID: aaa60e8ea12e
Revises: 5c029d9ef925
Create Date: 2020-03-04 21:56:32.651065
"""

from alembic import op

revision = "aaa60e8ea12e"
down_revision = "5c029d9ef925"


def upgrade():
    op.create_unique_constraint(
        "_roles_user_project_uc", "roles", ["user_id", "project_id"]
    )


def downgrade():
    op.drop_constraint("_roles_user_project_uc", "roles", type_="unique")
