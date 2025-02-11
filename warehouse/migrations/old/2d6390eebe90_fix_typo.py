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
Fix typo

Revision ID: 2d6390eebe90
Revises: 08447ab49999
Create Date: 2018-11-12 03:05:20.555925
"""

from alembic import op

revision = "2d6390eebe90"
down_revision = "08447ab49999"


def upgrade():
    op.create_index(
        "journals_submitted_date_id_idx",
        "journals",
        ["submitted_date", "id"],
        unique=False,
    )
    op.drop_index("journakls_submitted_date_id_idx", table_name="journals")


def downgrade():
    op.create_index(
        "journakls_submitted_date_id_idx",
        "journals",
        ["submitted_date", "id"],
        unique=False,
    )
    op.drop_index("journals_submitted_date_id_idx", table_name="journals")
