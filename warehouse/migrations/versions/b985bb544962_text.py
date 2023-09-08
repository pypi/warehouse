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
Rename package_type enum to packagetype

Revision ID: b985bb544962
Revises: 757731924605
Create Date: 2023-09-08 18:06:56.085062
"""

from alembic import op

revision = "b985bb544962"
down_revision = "757731924605"


def upgrade():
    op.execute("ALTER TYPE package_type RENAME TO packagetype")


def downgrade():
    op.execute("ALTER TYPE packagetype RENAME TO package_type ")
