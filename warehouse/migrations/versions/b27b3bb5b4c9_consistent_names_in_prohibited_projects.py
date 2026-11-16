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
consistent names in prohibited projects

Revision ID: b27b3bb5b4c9
Revises: 6cac7b706953
Create Date: 2025-02-24 19:31:38.064454
"""

from alembic import op

revision = "b27b3bb5b4c9"
down_revision = "6cac7b706953"


def upgrade():
    op.execute(
        """
        ALTER TABLE prohibited_project_names
        RENAME CONSTRAINT blacklist_name_key TO prohibited_project_names_name_key
    """
    )

    op.execute(
        """
        ALTER TABLE prohibited_project_names
        RENAME CONSTRAINT blacklist_pkey TO prohibited_project_names_pkey
    """
    )

    op.execute(
        """
        ALTER TABLE prohibited_project_names
        RENAME CONSTRAINT blacklist_blacklisted_by_fkey
        TO prohibited_project_names_prohibited_by_fkey
    """
    )

    op.execute(
        """ CREATE OR REPLACE FUNCTION ensure_normalized_prohibited_name()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.name = normalize_pep426_name(NEW.name);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        DROP TRIGGER normalize_blacklist ON prohibited_project_names
    """
    )

    op.execute(
        """
        CREATE TRIGGER normalize_prohibited_project_name
        BEFORE INSERT OR UPDATE ON prohibited_project_names
        FOR EACH ROW EXECUTE FUNCTION public.ensure_normalized_prohibited_name()
    """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS public.ensure_normalized_blacklist()
    """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE prohibited_project_names
        RENAME CONSTRAINT prohibited_project_names_name_key TO blacklist_name_key
    """
    )

    op.execute(
        """
        ALTER TABLE prohibited_project_names
        RENAME CONSTRAINT prohibited_project_names_pkey TO blacklist_pkey
    """
    )

    op.execute(
        """
        ALTER TABLE prohibited_project_names
        RENAME CONSTRAINT prohibited_project_names_prohibited_by_fkey
        TO blacklist_blacklisted_by_fkey
    """
    )

    op.execute(
        """
        DROP TRIGGER normalize_prohibited_project_name ON prohibited_project_names
    """
    )

    op.execute(
        """
        CREATE TRIGGER normalize_blacklist
        BEFORE INSERT OR UPDATE ON prohibited_project_names
        FOR EACH ROW EXECUTE FUNCTION public.ensure_normalized_blacklist()
    """
    )
