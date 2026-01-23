# SPDX-License-Identifier: Apache-2.0
"""
Drop unused indexes

Revision ID: 6a6eb0a95603
Revises: 4e7d5154cb0c
Create Date: 2018-08-15 20:01:42.232010
"""

from alembic import op

revision = "6a6eb0a95603"
down_revision = "4e7d5154cb0c"


def upgrade():
    op.drop_index("journals_latest_releases", table_name="journals")
    op.drop_index("rel_class_name_idx", table_name="release_classifiers")
    op.drop_index("rel_dep_name_idx", table_name="release_dependencies")
    op.drop_index("release_files_packagetype_idx", table_name="release_files")
    op.drop_index("release_pypi_hidden_idx", table_name="releases")
    op.drop_index("releases_name_ts_idx", table_name="releases")
    op.drop_index("releases_summary_ts_idx", table_name="releases")
    op.drop_index("ix_ses_emails_status", table_name="ses_emails")


def downgrade():
    op.create_index("ix_ses_emails_status", "ses_emails", ["status"], unique=False)
    op.create_index(
        "release_pypi_hidden_idx", "releases", ["_pypi_hidden"], unique=False
    )
    op.create_index(
        "release_files_packagetype_idx", "release_files", ["packagetype"], unique=False
    )
    op.create_index("rel_dep_name_idx", "release_dependencies", ["name"], unique=False)
    op.create_index("rel_class_name_idx", "release_classifiers", ["name"], unique=False)
    op.create_index(
        "journals_latest_releases",
        "journals",
        ["submitted_date", "name", "version"],
        unique=False,
    )

    op.execute(""" CREATE INDEX releases_name_ts_idx
            ON releases
            USING gin
            (to_tsvector('english'::regconfig, name))
        """)

    op.execute(""" CREATE INDEX releases_summary_ts_idx
            ON releases
            USING gin
            (to_tsvector('english'::regconfig, summary));
        """)
