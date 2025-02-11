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
Cascade User deletion to GPG keys

Revision ID: 8fd3400c760f
Revises: c0302a8a0878
Create Date: 2018-03-09 23:27:06.222073
"""

from alembic import op

revision = "8fd3400c760f"
down_revision = "c0302a8a0878"


def upgrade():
    op.drop_constraint(
        "accounts_gpgkey_user_id_fkey", "accounts_gpgkey", type_="foreignkey"
    )
    op.create_foreign_key(
        "accounts_gpgkey_user_id_fkey",
        "accounts_gpgkey",
        "accounts_user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
        initially="DEFERRED",
        deferrable=True,
    )


def downgrade():
    op.drop_constraint(
        "accounts_gpgkey_user_id_fkey", "accounts_gpgkey", type_="foreignkey"
    )
    op.create_foreign_key(
        "accounts_gpgkey_user_id_fkey",
        "accounts_gpgkey",
        "accounts_user",
        ["user_id"],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )
