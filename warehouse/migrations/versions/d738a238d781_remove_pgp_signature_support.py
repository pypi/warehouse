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
Remove PGP signature support

Revision ID: d738a238d781
Revises: ab536b1853f0
Create Date: 2023-05-21 14:46:11.845339
"""

from alembic import op

revision = "d738a238d781"
down_revision = "ab536b1853f0"


def upgrade():
    op.drop_column("release_files", "has_signature")


def downgrade():
    raise RuntimeError("Cannot undelete data!")
