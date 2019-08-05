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
WebAuthn and Macaroon constraints

Revision ID: 48def930fcfd
Revises: 5ea52744d154
Create Date: 2019-07-26 17:55:41.802528
"""

from alembic import op

revision = "48def930fcfd"
down_revision = "5ea52744d154"


def upgrade():
    op.create_unique_constraint(
        "_user_macaroons_description_uc", "macaroons", ["description", "user_id"]
    )
    op.create_unique_constraint(
        "_user_security_keys_label_uc", "user_security_keys", ["label", "user_id"]
    )
    op.drop_index("user_security_keys_label_key", table_name="user_security_keys")


def downgrade():
    op.create_index(
        "user_security_keys_label_key", "user_security_keys", ["user_id"], unique=False
    )
    op.drop_constraint(
        "_user_security_keys_label_uc", "user_security_keys", type_="unique"
    )
    op.drop_constraint("_user_macaroons_description_uc", "macaroons", type_="unique")
