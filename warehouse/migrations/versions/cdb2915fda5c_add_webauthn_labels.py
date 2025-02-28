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
add webauthn labels

Revision ID: cdb2915fda5c
Revises: af7dca2bb2fe
Create Date: 2019-06-08 16:31:41.681380
"""

import sqlalchemy as sa

from alembic import op

revision = "cdb2915fda5c"
down_revision = "af7dca2bb2fe"


def upgrade():
    op.add_column("user_security_keys", sa.Column("label", sa.String(), nullable=False))
    op.create_index(
        "user_security_keys_label_key", "user_security_keys", ["user_id"], unique=False
    )


def downgrade():
    op.drop_index("user_security_keys_label_key", table_name="user_security_keys")
    op.drop_column("user_security_keys", "label")
