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
Add a requires_python column to release_files; pursuant to enabling PEP 503.

Revision ID: be4cf6b58557
Revises: 3d2b8a42219a
Create Date: 2016-09-15 04:12:53.430363
"""

import sqlalchemy as sa

from alembic import op

revision = "be4cf6b58557"
down_revision = "3d2b8a42219a"


def upgrade():
    """
    Add column `requires_python` in the `release_files` table.
    """
    op.add_column(
        "release_files", sa.Column("requires_python", sa.Text(), nullable=True)
    )

    # Populate the column with content from release.requires_python.
    op.execute(
        """ UPDATE release_files
            SET requires_python = releases.requires_python
            FROM releases
            WHERE
                release_files.name=releases.name
                AND release_files.version=releases.version;
        """
    )

    # Setup a trigger function to ensure that requires_python value on
    # releases is always canonical.
    op.execute(
        """CREATE OR REPLACE FUNCTION update_release_files_requires_python()
            RETURNS TRIGGER AS $$
            BEGIN
                UPDATE
                    release_files
                SET
                    requires_python = releases.requires_python
                FROM releases
                WHERE
                    release_files.name=releases.name
                    AND release_files.version=releases.version
                    AND release_files.name = NEW.name
                    AND releases.version = NEW.version;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
        """
    )

    # Establish a trigger such that on INSERT/UPDATE on releases we update
    # release_files with the appropriate requires_python values.
    op.execute(
        """ CREATE TRIGGER releases_requires_python
            AFTER INSERT OR UPDATE OF requires_python ON releases
            FOR EACH ROW
                EXECUTE PROCEDURE update_release_files_requires_python();
        """
    )


def downgrade():
    """
    Drop trigger and function that synchronize `releases`.
    """
    op.execute("DROP TRIGGER releases_requires_python ON releases")
    op.execute("DROP FUNCTION update_release_files_requires_python()")
    op.drop_column("release_files", "requires_python")
