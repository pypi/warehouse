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
create index on roles table for project_id

Revision ID: b6d057388dd9
Revises: 80018e46c5a4
Create Date: 2020-11-09 17:13:40.639721
"""

import sqlalchemy as sa

from alembic import op

revision = "b6d057388dd9"
down_revision = "80018e46c5a4"


def upgrade():
    op.create_index("roles_project_id_idx", "roles", ["project_id"], unique=False)


def downgrade():
    op.drop_index("roles_project_id_idx", table_name="roles")
