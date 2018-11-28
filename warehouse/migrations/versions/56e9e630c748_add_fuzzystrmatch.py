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
Add fuzzystrmatch

Revision ID: 56e9e630c748
Revises: e82c3a017d60
Create Date: 2018-08-28 19:00:47.606523
"""

from alembic import op

revision = "56e9e630c748"
down_revision = "e82c3a017d60"


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch")


def downgrade():
    pass
