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
Remove useless index

Revision ID: 7750037b351a
Revises: f449e5bff5a5
Create Date: 2016-12-17 21:10:27.781900
"""

from alembic import op


revision = "7750037b351a"
down_revision = "f449e5bff5a5"


def upgrade():
    op.drop_index("release_files_name_idx", table_name="release_files")


def downgrade():
    op.create_index(
        "release_files_name_idx",
        "release_files",
        ["name"],
        unique=False,
    )
