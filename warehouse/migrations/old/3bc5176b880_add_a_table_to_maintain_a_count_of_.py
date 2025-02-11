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
Add a table to maintain a count of table rows

Revision ID: 3bc5176b880
Revises: 18e4cf2bb3e
Create Date: 2015-11-15 15:10:38.681814
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "3bc5176b880"
down_revision = "18e4cf2bb3e"


def upgrade():
    op.create_table(
        "row_counts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("table_name", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "count", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

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

    op.execute("LOCK TABLE packages IN SHARE ROW EXCLUSIVE MODE")
    op.execute("LOCK TABLE releases IN SHARE ROW EXCLUSIVE MODE")
    op.execute("LOCK TABLE release_files IN SHARE ROW EXCLUSIVE MODE")
    op.execute("LOCK TABLE accounts_user IN SHARE ROW EXCLUSIVE MODE")

    op.execute(
        """ CREATE TRIGGER update_row_count
            AFTER INSERT OR DELETE ON packages
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
            AFTER INSERT OR DELETE ON accounts_user
            FOR EACH ROW
            EXECUTE PROCEDURE count_rows();
        """
    )

    op.execute(
        """ INSERT INTO row_counts (table_name, count)
            VALUES  ('packages',  (SELECT COUNT(*) FROM packages));
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
            VALUES  ('accounts_user',  (SELECT COUNT(*) FROM accounts_user));
        """
    )


def downgrade():
    op.execute("DROP TRIGGER update_row_count ON accounts_user")
    op.execute("DROP TRIGGER update_row_count ON release_files")
    op.execute("DROP TRIGGER update_row_count ON releases")
    op.execute("DROP TRIGGER update_row_count ON packages")
    op.execute("DROP FUNCTION count_rows()")
    op.drop_table("row_counts")
