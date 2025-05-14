# SPDX-License-Identifier: Apache-2.0
"""
Disallow multiple sdists for a release

Revision ID: f449e5bff5a5
Revises: f404a67e0370
Create Date: 2016-12-17 17:10:31.252165
"""

import sqlalchemy as sa

from alembic import op

revision = "f449e5bff5a5"
down_revision = "f404a67e0370"


def upgrade():
    op.add_column(
        "release_files", sa.Column("allow_multiple_sdist", sa.Boolean(), nullable=True)
    )

    # This is a bit complicated, but essentially we're going to find any set of
    # (name, version) that has more than one sdist uploaded for it. Then we
    # loop over that and we flag all but one of those duplicate sdists to allow
    # it to be duplicated. It is important that we only set this flag on N -1
    # because if we set it on N, then our unique index would not see *any*
    # existing uploads for that project and would allow one more duplicate to
    # be uploaded.
    op.execute(
        """ DO $$
            DECLARE
                row record;
            BEGIN
                FOR row IN SELECT name, version, COUNT(*) as sdist_count
                            FROM release_files
                            WHERE packagetype = 'sdist'
                            GROUP BY name, version
                            HAVING COUNT(*) > 1
                LOOP
                    UPDATE release_files
                    SET allow_multiple_sdist = true
                    FROM (
                        SELECT id
                        FROM release_files
                        WHERE name = row.name
                            AND version = row.version
                            AND packagetype = 'sdist'
                        ORDER BY upload_time
                        LIMIT (row.sdist_count - 1)
                    ) s
                    WHERE release_files.id = s.id;
                END LOOP;
            END $$;
        """
    )

    op.execute(
        """ UPDATE release_files
            SET allow_multiple_sdist = false
            WHERE allow_multiple_sdist IS NULL
        """
    )

    op.alter_column(
        "release_files",
        "allow_multiple_sdist",
        nullable=False,
        server_default=sa.text("false"),
    )

    op.create_index(
        "release_files_single_sdist",
        "release_files",
        ["name", "version", "packagetype"],
        unique=True,
        postgresql_where=sa.text(
            "packagetype = 'sdist' AND allow_multiple_sdist = false"
        ),
    )


def downgrade():
    op.drop_index("release_files_single_sdist", table_name="release_files")
    op.drop_column("release_files", "allow_multiple_sdist")
