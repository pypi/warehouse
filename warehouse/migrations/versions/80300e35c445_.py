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
empty message

Revision ID: 80300e35c445
Revises: 8c8be2c0e69e
Create Date: 2016-08-25 00:18:42.382362
"""

from alembic import op
import sqlalchemy as sa


revision = '80300e35c445'
down_revision = '8c8be2c0e69e'

def upgrade():
    op.execute(
        """ CREATE MATERIALIZED VIEW requires_python_view AS
        SELECT release_files.name, filename, releases.requires_python, md5_digest
        FROM release_files
        INNER JOIN releases
            ON release_files.version=releases.version
            AND release_files.name=releases.name;

        CREATE INDEX requires_python_name_ix ON requires_python_view(name);

        CREATE OR REPLACE FUNCTION refresh_mat_view()
        RETURNS TRIGGER LANGUAGE plpgsql
        AS $$
        BEGIN
            REFRESH MATERIALIZED VIEW requires_python_view;
            RETURN NULL;
        END $$;

        CREATE TRIGGER refresh_req_python_release_files
            AFTER INSERT OR UPDATE OR DELETE
            ON release_files FOR EACH STATEMENT 
            EXECUTE PROCEDURE refresh_mat_view();

        CREATE TRIGGER refresh_req_python_releases
            AFTER INSERT OR UPDATE OR DELETE
            ON releases FOR EACH STATEMENT 
            EXECUTE PROCEDURE refresh_mat_view();
        """
    )


def downgrade():

    op.execute(
        """ DROP INDEX requires_python_name_ix FROM requires_python_view;
            DROP materialized view requires_python_view;
            DROP TRIGGER refresh_req_python_release_files FROM release_files;
            DROP TRIGGER refresh_req_python_releases FROM releases;
        """
    )
   
