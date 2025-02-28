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
create missing primary key constraints

Revision ID: b5bb5d08543d
Revises: 08aedc089eaf
Create Date: 2019-12-19 14:27:47.230249
"""

from alembic import op

revision = "b5bb5d08543d"
down_revision = "08aedc089eaf"


def upgrade():
    op.create_primary_key(None, "release_files", ["id"])
    op.create_primary_key(None, "release_dependencies", ["id"])
    op.create_primary_key(None, "roles", ["id"])


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
