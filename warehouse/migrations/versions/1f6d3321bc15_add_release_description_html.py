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
Add Release.description_html

Revision ID: 1f6d3321bc15
Revises: 42f0409bb702
Create Date: 2019-05-08 02:14:47.994566
"""

import sqlalchemy as sa

from alembic import op

revision = "1f6d3321bc15"
down_revision = "42f0409bb702"


def upgrade():
    op.add_column("releases", sa.Column("description_html", sa.Text(), nullable=True))
    op.add_column(
        "releases", sa.Column("description_html_rendered_by", sa.Text(), nullable=True)
    )


def downgrade():
    op.drop_column("releases", "description_html_rendered_by")
    op.drop_column("releases", "description_html")
