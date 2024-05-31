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
Remove count_rows() triggers

Revision ID: cec0316503a5
Revises: 78ecf599841c
Create Date: 2024-05-30 16:46:07.355604
"""

from alembic import op

revision = "cec0316503a5"
down_revision = "78ecf599841c"


def upgrade():
    op.execute("DROP TRIGGER update_row_count ON users")
    op.execute("DROP TRIGGER update_row_count ON release_files")
    op.execute("DROP TRIGGER update_row_count ON releases")
    op.execute("DROP TRIGGER update_row_count ON projects")
    op.execute("DROP FUNCTION count_rows()")


def downgrade():
    op.execute(
        """ CREATE FUNCTION count_rows()
            RETURNS TRIGGER AS
            '
                BEGIN
                    IF TG_OP = ''INSERT'' THEN
                        UPDATE row_counts
                        SET count = count + 1
                        WHERE table_name = TG_RELNAME;
                    ELSIF TG_OP = ''DELETE'' THEN
                        UPDATE row_counts
                        SET count = count - 1
                        WHERE table_name = TG_RELNAME;
                    END IF;

                    RETURN NULL;
                END;
            ' LANGUAGE plpgsql;
        """
    )

    op.execute("LOCK TABLE projects IN SHARE ROW EXCLUSIVE MODE")
    op.execute("LOCK TABLE releases IN SHARE ROW EXCLUSIVE MODE")
    op.execute("LOCK TABLE release_files IN SHARE ROW EXCLUSIVE MODE")
    op.execute("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE")

    op.execute(
        """ CREATE TRIGGER update_row_count
            AFTER INSERT OR DELETE ON projects
            FOR EACH ROW
            EXECUTE PROCEDURE count_rows();
        """
    )

    op.execute(
        """ CREATE TRIGGER update_row_count
            AFTER INSERT OR DELETE ON releases
            FOR EACH ROW
            EXECUTE PROCEDURE count_rows();
        """
    )

    op.execute(
        """ CREATE TRIGGER update_row_count
            AFTER INSERT OR DELETE ON release_files
            FOR EACH ROW
            EXECUTE PROCEDURE count_rows();
        """
    )

    op.execute(
        """ CREATE TRIGGER update_row_count
            AFTER INSERT OR DELETE ON users
            FOR EACH ROW
            EXECUTE PROCEDURE count_rows();
        """
    )

    op.execute(
        """ INSERT INTO row_counts (table_name, count)
            VALUES  ('projects',  (SELECT COUNT(*) FROM projects));
        """
    )

    op.execute(
        """ INSERT INTO row_counts (table_name, count)
            VALUES  ('releases',  (SELECT COUNT(*) FROM releases));
        """
    )

    op.execute(
        """ INSERT INTO row_counts (table_name, count)
            VALUES  ('release_files',  (SELECT COUNT(*) FROM release_files));
        """
    )

    op.execute(
        """ INSERT INTO row_counts (table_name, count)
            VALUES  ('users',  (SELECT COUNT(*) FROM users));
        """
    )
