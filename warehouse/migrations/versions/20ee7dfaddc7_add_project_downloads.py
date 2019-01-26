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
Add `downloads_last_30_days` column on project for indexing.

Revision ID: 20ee7dfaddc7
Revises: 3db69c05dd11
Create Date: 2019-01-06 16:17:43.846366
"""

import sqlalchemy as sa

from alembic import op

revision = "20ee7dfaddc7"
down_revision = "3db69c05dd11"

# Note: It is VERY important to ensure that a migration does not lock for a
#       long period of time and to ensure that each individual migration does
#       not break compatibility with the *previous* version of the code base.
#       This is because the migrations will be ran automatically as part of the
#       deployment process, but while the previous version of the code is still
#       up and running. Thus backwards incompatible changes must be broken up
#       over multiple migrations inside of multiple pull requests in order to
#       phase them in over multiple deploys.


def upgrade():
    op.add_column(
        "projects", sa.Column("downloads_last_30_days", sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column("projects", "downloads_last_30_days")
