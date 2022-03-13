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
Add missing indexes

Revision ID: 19ca1c78e613
Revises: 0e8f7729161a
Create Date: 2020-06-16 22:29:31.341596
"""

from alembic import op

revision = "19ca1c78e613"
down_revision = "0e8f7729161a"


def upgrade():
    op.create_index(
        op.f("ix_prohibited_project_names_prohibited_by"),
        "prohibited_project_names",
        ["prohibited_by"],
        unique=False,
    )
    op.drop_index("ix_blacklist_blacklisted_by", table_name="prohibited_project_names")


def downgrade():
    op.create_index(
        "ix_blacklist_blacklisted_by",
        "prohibited_project_names",
        ["prohibited_by"],
        unique=False,
    )
    op.drop_index(
        op.f("ix_prohibited_project_names_prohibited_by"),
        table_name="prohibited_project_names",
    )
