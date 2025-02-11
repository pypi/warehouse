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
Cascade Role deletion

Revision ID: c0682028c857
Revises: 1fdf5dc6bbf3
Create Date: 2018-03-08 19:15:01.860863
"""

from alembic import op

revision = "c0682028c857"
down_revision = "1fdf5dc6bbf3"


def upgrade():
    op.drop_constraint("roles_package_name_fkey", "roles", type_="foreignkey")
    op.drop_constraint("roles_user_name_fkey", "roles", type_="foreignkey")
    op.create_foreign_key(
        "roles_package_name_fkey",
        "roles",
        "packages",
        ["package_name"],
        ["name"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "roles_user_name_fkey",
        "roles",
        "accounts_user",
        ["user_name"],
        ["username"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(None, "roles", type_="foreignkey")
    op.drop_constraint(None, "roles", type_="foreignkey")
    op.create_foreign_key(
        "roles_user_name_fkey",
        "roles",
        "accounts_user",
        ["user_name"],
        ["username"],
        onupdate="CASCADE",
    )
    op.create_foreign_key(
        "roles_package_name_fkey",
        "roles",
        "packages",
        ["package_name"],
        ["name"],
        onupdate="CASCADE",
    )
