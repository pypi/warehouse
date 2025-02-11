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
Remove caveats to permissions

Revision ID: 84262e097c26
Revises: f345394c444f
Create Date: 2022-04-05 18:35:57.325801
"""

from alembic import op

revision = "84262e097c26"
down_revision = "f345394c444f"


def upgrade():
    op.alter_column("macaroons", "caveats", new_column_name="permissions_caveat")


def downgrade():
    op.alter_column("macaroons", "permissions_caveat", new_column_name="caveats")
