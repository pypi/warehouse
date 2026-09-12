# SPDX-License-Identifier: Apache-2.0
"""
Cascade delete release_descriptions when a release is removed

The `releases.description_id` foreign key points up to `release_descriptions`,
so the `ON DELETE CASCADE` from `projects` to `releases` (and any other path
that deletes a release without the ORM `delete-orphan` cascade) never reaches
the description, leaving it orphaned.

Enforce the cleanup at the database level with an `AFTER DELETE` trigger on
`releases` that removes the description it referenced.

See: https://github.com/pypi/warehouse/issues/14825

Revision ID: b9d3c5e8f1a2
Revises: a8038ce10051
Create Date: 2026-06-24 14:30:00.000000
"""

from alembic import op

revision = "b9d3c5e8f1a2"
down_revision = "a8038ce10051"


def upgrade():
    op.execute(
        """CREATE OR REPLACE FUNCTION delete_orphaned_release_description()
        RETURNS TRIGGER AS $$
        BEGIN
            DELETE FROM release_descriptions WHERE id = OLD.description_id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """CREATE TRIGGER releases_delete_orphaned_description
            AFTER DELETE ON releases
            FOR EACH ROW EXECUTE PROCEDURE delete_orphaned_release_description();
        """
    )


def downgrade():
    op.execute("DROP TRIGGER releases_delete_orphaned_description ON releases;")
    op.execute("DROP FUNCTION delete_orphaned_release_description;")
