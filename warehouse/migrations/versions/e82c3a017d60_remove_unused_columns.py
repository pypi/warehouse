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
Remove unused columns

Revision ID: e82c3a017d60
Revises: 62f6becc7653
Create Date: 2018-08-17 16:23:08.775818
"""

from alembic import op

revision = "e82c3a017d60"
down_revision = "62f6becc7653"


def upgrade():
    op.drop_column("accounts_user", "is_staff")
    op.drop_column("packages", "hosting_mode")
    op.drop_column("packages", "autohide")
    op.drop_column("packages", "bugtrack_url")
    op.drop_column("packages", "comments")
    op.drop_column("packages", "stable_version")
    op.drop_column("release_files", "downloads")
    op.drop_column("releases", "description_from_readme")
    op.drop_column("releases", "_pypi_hidden")


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
