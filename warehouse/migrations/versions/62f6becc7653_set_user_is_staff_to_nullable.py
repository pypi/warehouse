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
Set User.is_staff to nullable

Revision ID: 62f6becc7653
Revises: 522918187b73
Create Date: 2018-08-17 16:16:20.397865
"""

from alembic import op

revision = "62f6becc7653"
down_revision = "522918187b73"


def upgrade():
    op.alter_column("accounts_user", "is_staff", nullable=True)


def downgrade():
    op.alter_column("accounts_user", "is_staff", nullable=False)
