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
Remove duplicates from release_classifiers

Revision ID: 7f6bed4f4345
Revises: a8ebe73ccaf2
Create Date: 2023-08-16 22:56:54.898269
"""

from alembic import op

revision = "7f6bed4f4345"
down_revision = "a8ebe73ccaf2"


def upgrade():
    op.execute("SET statement_timeout = 60000")  # 60s
    op.execute("SET lock_timeout = 60000")  # 60s

    op.execute(
        """
        DELETE FROM release_classifiers a USING (
            SELECT MIN(ctid) as ctid, release_id, trove_id
            FROM release_classifiers
            GROUP BY release_id, trove_id HAVING COUNT(*) > 1
            LIMIT 4453 -- 4453 is the number of duplicates in production
        ) b
        WHERE a.release_id = b.release_id
        AND a.trove_id = b.trove_id
        AND a.ctid <> b.ctid;
        """
    )


def downgrade():
    # No going back.
    pass
