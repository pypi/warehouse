# SPDX-License-Identifier: Apache-2.0
"""
update_project_size_on_release_removal

Revision ID: 87509f4ae027
Revises: bc8f7b526961
Create Date: 2020-07-06 21:37:52.833331
"""

from alembic import op

revision = "87509f4ae027"
down_revision = "bc8f7b526961"


def upgrade():
    op.execute(
        """CREATE OR REPLACE FUNCTION projects_total_size_release_files()
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

    op.execute(
        """CREATE OR REPLACE FUNCTION projects_total_size_releases()
        RETURNS TRIGGER AS $$
        DECLARE
            _project_id uuid;
        BEGIN
            _project_id := OLD.project_id;
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

    op.execute(
        """CREATE TRIGGER update_project_total_size_release_files
            AFTER INSERT OR UPDATE OR DELETE ON release_files
            FOR EACH ROW EXECUTE PROCEDURE projects_total_size_release_files();
        """
    )
    op.execute(
        """CREATE TRIGGER update_project_total_size_releases
            AFTER DELETE ON releases
            FOR EACH ROW EXECUTE PROCEDURE projects_total_size_releases();
        """
    )

    op.execute("DROP TRIGGER update_project_total_size ON release_files;")
    op.execute("DROP FUNCTION projects_total_size;")

    # Refresh to reset projects that fell out of sync
    op.execute(
        """WITH project_totals AS (
                SELECT
                    p.id as project_id,
                    sum(size) as project_total
                FROM
                    release_files rf
                    JOIN releases r on rf.release_id = r.id
                    JOIN projects p on r.project_id = p.id
                GROUP BY
                    p.id
            )
            UPDATE projects AS p
            SET total_size = project_totals.project_total
            FROM project_totals
            WHERE project_totals.project_id = p.id;
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

    op.execute(
        """CREATE TRIGGER update_project_total_size
            AFTER INSERT OR UPDATE OR DELETE ON release_files
            FOR EACH ROW EXECUTE PROCEDURE projects_total_size();
        """
    )

    op.execute("DROP TRIGGER update_project_total_size_releases ON releases;")
    op.execute("DROP TRIGGER update_project_total_size_release_files ON release_files;")
    op.execute("DROP FUNCTION projects_total_size_release_files;")
    op.execute("DROP FUNCTION projects_total_size_releases;")
