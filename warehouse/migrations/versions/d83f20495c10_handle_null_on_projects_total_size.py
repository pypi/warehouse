# SPDX-License-Identifier: Apache-2.0
"""
handle_null_on_projects_total_size

Revision ID: d83f20495c10
Revises: 48def930fcfd
Create Date: 2019-08-10 20:47:10.155339
"""

from alembic import op

revision = "d83f20495c10"
down_revision = "48def930fcfd"


def upgrade():
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
            SELECT COALESCE(SUM(release_files.size), 0) AS project_total_size
            FROM release_files WHERE release_id IN
                (SELECT id FROM releases WHERE releases.project_id = _project_id)
            ) AS t
            WHERE id=_project_id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade():
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
