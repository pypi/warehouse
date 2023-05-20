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
create upload_limit constraint

Revision ID: 1d88dd9242e1
Revises: aa3a4757f33a
Create Date: 2022-12-07 14:15:34.126364
"""

from alembic import op

revision = "1d88dd9242e1"
down_revision = "aa3a4757f33a"


def upgrade():
    op.create_check_constraint(
        "projects_upload_limit_max_value",
        "projects",
        "upload_limit <= 1073741824",
    )


def downgrade():
    op.drop_constraint(
        "projects_upload_limit_max_value",
        "projects",
    )
