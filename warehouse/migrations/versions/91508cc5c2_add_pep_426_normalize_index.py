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
Add Index for normalized PEP 426 names which enforces uniqueness.

Revision ID: 91508cc5c2
Revises: 20f4dbe11e9
Create Date: 2015-04-04 23:55:27.024988
"""

from alembic import op

revision = "91508cc5c2"
down_revision = "20f4dbe11e9"


def upgrade():
    op.execute(
        """
        CREATE UNIQUE INDEX project_name_pep426_normalized
            ON packages
            (normalize_pep426_name(name))
    """
    )


def downgrade():
    op.execute("DROP INDEX project_name_pep426_normalized")
