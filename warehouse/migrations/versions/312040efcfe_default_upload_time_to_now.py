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
default upload_time to now

Revision ID: 312040efcfe
Revises: 57b1053998d
Create Date: 2015-06-13 01:44:23.445650
"""

from alembic import op
import sqlalchemy as sa


revision = "312040efcfe"
down_revision = "57b1053998d"


def upgrade():
    op.alter_column("release_files", "upload_time", server_default=sa.text("now()"))


def downgrade():
    op.alter_column("release_files", "upload_time", server_default=None)
