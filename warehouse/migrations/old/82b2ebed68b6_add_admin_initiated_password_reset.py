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
add admin initiated password reset

Revision ID: 82b2ebed68b6
Revises: 14ad61e054cf
Create Date: 2024-07-09 21:18:50.979790
"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "82b2ebed68b6"
down_revision = "14ad61e054cf"


def upgrade():
    op.execute("SET statement_timeout = 60000")
    op.execute("SET lock_timeout = 10000")
    op.sync_enum_values(
        "public",
        "disablereason",
        ["password compromised", "account frozen", "admin initiated"],
        [
            TableReference(
                table_schema="public", table_name="users", column_name="disabled_for"
            )
        ],
        enum_values_to_rename=[],
    )


def downgrade():
    op.execute("SET statement_timeout = 60000")
    op.execute("SET lock_timeout = 10000")
    op.sync_enum_values(
        "public",
        "disablereason",
        ["password compromised", "account frozen"],
        [
            TableReference(
                table_schema="public", table_name="users", column_name="disabled_for"
            )
        ],
        enum_values_to_rename=[],
    )
