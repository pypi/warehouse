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
Drop titan_promo_code table

Revision ID: 90f6ee9298db
Revises: d0f67adbcb80
Create Date: 2022-10-03 18:48:39.327937
"""


from alembic import op

revision = "90f6ee9298db"
down_revision = "d0f67adbcb80"


def upgrade():
    op.drop_index("ix_user_titan_codes_user_id", table_name="user_titan_codes")
    op.drop_table("user_titan_codes")


def downgrade():
    raise RuntimeError("Can't roll back")
