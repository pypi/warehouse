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
add ondelete=cascade for description_urls

Revision ID: b75709859292
Revises: 7165e957cddc
Create Date: 2018-02-19 02:26:37.944376
"""

from alembic import op

revision = "b75709859292"
down_revision = "7165e957cddc"


def upgrade():
    op.drop_constraint(
        "description_urls_name_fkey", "description_urls", type_="foreignkey"
    )
    op.create_foreign_key(
        "description_urls_name_fkey",
        "description_urls",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(
        "description_urls_name_fkey", "description_urls", type_="foreignkey"
    )
    op.create_foreign_key(
        "description_urls_name_fkey",
        "description_urls",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
    )
