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
Rename table for prohibited project names.

Revision ID: 0e8f7729161a
Revises: 30a7791fea33
Create Date: 2020-06-02 16:16:21.043443
"""

from alembic import op

revision = "0e8f7729161a"
down_revision = "30a7791fea33"


def upgrade():
    op.alter_column("blacklist", "blacklisted_by", new_column_name="prohibited_by")
    op.rename_table("blacklist", "prohibited_project_names")


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
