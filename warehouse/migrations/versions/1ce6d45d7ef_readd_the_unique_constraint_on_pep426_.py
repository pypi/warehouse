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
readd the unique constraint on pep426 normalization

Revision ID: 1ce6d45d7ef
Revises: 23a3c4ffe5d
Create Date: 2015-06-04 23:09:11.612200
"""

from alembic import op

revision = "1ce6d45d7ef"
down_revision = "23a3c4ffe5d"


def upgrade():
    op.execute(
        """ CREATE UNIQUE INDEX project_name_pep426_normalized
            ON packages
            (normalize_pep426_name(name))
        """
    )


def downgrade():
    op.execute("DROP INDEX project_name_pep426_normalized")
