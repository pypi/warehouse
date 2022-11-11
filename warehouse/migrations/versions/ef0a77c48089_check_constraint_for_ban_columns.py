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
check_constraint for ban columns

Revision ID: ef0a77c48089
Revises: f7d91bbfd59e
Create Date: 2022-11-10 20:14:30.253975
"""

from alembic import op

revision = "ef0a77c48089"
down_revision = "f7d91bbfd59e"


def upgrade():
    op.create_check_constraint(
        "ip_addresses_ban_constraints",
        table_name="ip_addresses",
        condition=(
            "(is_banned AND ban_reason IS NOT NULL AND ban_date IS NOT NULL)"
            "OR (NOT is_banned AND ban_reason IS NULL AND ban_date IS NULL)"
        ),
    )


def downgrade():
    op.drop_constraint(
        "ip_addresses_ban_constraints",
        table_name="ip_addresses",
    )
