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
Add UnverifyReason.DomainInvalid

Revision ID: 082def83d89f
Revises: 13c1c0ac92e9
Create Date: 2025-04-30 20:13:58.084316
"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "082def83d89f"
down_revision = "13c1c0ac92e9"


def upgrade():
    op.sync_enum_values(
        enum_schema="public",
        enum_name="unverifyreasons",
        new_values=[
            "spam complaint",
            "hard bounce",
            "soft bounce",
            "domain status invalid",
        ],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="user_emails",
                column_name="unverify_reason",
            )
        ],
        enum_values_to_rename=[],
    )


def downgrade():
    op.sync_enum_values(
        enum_schema="public",
        enum_name="unverifyreasons",
        new_values=["spam complaint", "hard bounce", "soft bounce"],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="user_emails",
                column_name="unverify_reason",
            )
        ],
        enum_values_to_rename=[],
    )
