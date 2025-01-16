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
Make processed column nullable, default to null

Revision ID: f1a3d0fd0eb9
Revises: 5440972cd89b
Create Date: 2025-01-16 22:44:14.824863
"""

import sqlalchemy as sa

from alembic import op

revision = "f1a3d0fd0eb9"
down_revision = "5440972cd89b"


def upgrade():
    op.alter_column(
        "missing_dataset_files", "processed", existing_type=sa.BOOLEAN(), nullable=True
    )


def downgrade():
    op.alter_column(
        "missing_dataset_files", "processed", existing_type=sa.BOOLEAN(), nullable=False
    )
