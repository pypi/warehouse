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

Revision ID: 80300e35c445
Revises: 8c8be2c0e69e
Create Date: 2016-08-25 00:18:42.382362
"""

from alembic import op
import sqlalchemy as sa


revision = '80300e35c445'
down_revision = '8c8be2c0e69e'

def upgrade():
    # Add column to represent the requires_python value in the release_files table.
    op.add_column("release_files", sa.Column("requires_python", sa.Text(), nullable=True))

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
    # releases is always canonical. Avoids infinite regress by checking
    # that the value is distinct from what it was before.
    op.execute(
        """CREATE OR REPLACE FUNCTION update_release_files_requires_python()
            RETURNS TRIGGER AS $$
            BEGIN
                IF OLD.requires_python IS DISTINCT FROM NEW.requires_python
                THEN
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
                END IF;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
        """
    )

    # Establish a trigger such that on INSERT/UPDATE on releases we update 
    # release_files with the appropriate requires_python values. 
    op.execute(
        """ CREATE TRIGGER releases_requires_python
            AFTER INSERT OR UPDATE ON releases 
            FOR EACH ROW EXECUTE PROCEDURE update_release_files_requires_python();
        """
    )

    # Establish a trigger such that on INSERT/UPDATE on release_files 
    # if someone changes the requires_python value, it is regenerated from 
    # releases. 
    op.execute(
        """ CREATE TRIGGER release_files_requires_python
            AFTER INSERT OR UPDATE ON release_files
            FOR EACH ROW EXECUTE PROCEDURE update_release_files_requires_python();
        """
    )

def downgrade():
    op.execute("DROP TRIGGER release_files_requires_python ON release_files")
    op.execute("DROP TRIGGER releases_requires_python ON releases")
    op.execute("DROP FUNCTION update_release_files_requires_python()")
    op.drop_column("release_files","requires_python")

   
