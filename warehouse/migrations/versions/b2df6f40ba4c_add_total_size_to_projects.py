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
add_total_size_to_projects

Revision ID: b2df6f40ba4c
Revises: 42f0409bb702
Create Date: 2019-05-07 15:07:25.696339
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy import sql

revision = "b2df6f40ba4c"
down_revision = "42f0409bb702"


def upgrade():
    op.add_column(
        "projects",
        sa.Column("total_size", sa.BigInteger(), server_default=sql.text("0")),
    )
    op.execute(
        """CREATE OR REPLACE FUNCTION projects_total_size()
        RETURNS TRIGGER AS $$
        DECLARE
            _release_id uuid;
            _project_id uuid;

        BEGIN
            IF TG_OP = 'INSERT' THEN
                _release_id := NEW.release_id;
            ELSEIF TG_OP = 'UPDATE' THEN
                _release_id := NEW.release_id;
            ELSIF TG_OP = 'DELETE' THEN
                _release_id := OLD.release_id;
            END IF;
            _project_id := (SELECT project_id
                            FROM releases
                            WHERE releases.id=_release_id);
            UPDATE projects
            SET total_size=t.project_total_size
            FROM (
            SELECT SUM(release_files.size) AS project_total_size
            FROM release_files WHERE release_id IN
                (SELECT id FROM releases WHERE releases.project_id = _project_id)
            ) AS t
            WHERE id=_project_id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """CREATE TRIGGER update_project_total_size
            AFTER INSERT OR UPDATE OR DELETE ON release_files
            FOR EACH ROW EXECUTE PROCEDURE projects_total_size();
        """
    )


def downgrade():
    op.execute("DROP TRIGGER update_project_total_size ON release_files;")
    op.execute("DROP FUNCTION projects_total_size;")
    op.drop_column("projects", "total_size")
