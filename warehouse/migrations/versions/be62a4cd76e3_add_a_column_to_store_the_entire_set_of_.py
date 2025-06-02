# SPDX-License-Identifier: Apache-2.0
"""
Add a column to store the entire set of serialized caveats

Revision ID: be62a4cd76e3
Revises: 812e14a4cddf
Create Date: 2024-01-20 16:28:31.573452
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "be62a4cd76e3"
down_revision = "a073e7979805"


def upgrade():
    op.execute("SET statement_timeout = 60000")  # 60s

    op.add_column(
        "macaroons",
        sa.Column(
            "caveats",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "The list of caveats that were attached to this Macaroon when we "
                "generated it. Users can add additional caveats at any time without "
                "communicating those additional caveats to us, which would not be "
                "reflected in this data, and thus this field must only be used for "
                "informational purposes and must not be used during the authorization "
                "or authentication process. Older Macaroons may be missing caveats as "
                "previously only the legacy permissions caveat were stored."
            ),
        ),
    )

    # Where our permissions_caveat is {"permission": "user"}, set our caveats to
    # [[3, str(user_id)]], which is a single RequestUser caveat where the user_id
    # is the attached user_id for this Macaroon.
    op.execute(
        """ UPDATE macaroons
            SET caveats = jsonb_build_array(jsonb_build_array(3, user_id::text))
            WHERE
                caveats IS NULL
                AND user_id IS NOT NULL
                AND permissions_caveat->>'permissions' = 'user'
        """
    )

    # Where our permissions_caveat is {"permission": [str, ...]}, set our caveats to
    # [[1, [str, ...]]], which is a single ProjectName caveat where the list of project
    # names is taken from the permissions_caveat.
    op.execute(
        """ UPDATE macaroons
            SET caveats = jsonb_build_array(
                jsonb_build_array(1, permissions_caveat->'permissions'->'projects')
            )
            WHERE
                caveats IS NULL
                AND jsonb_typeof(
                    permissions_caveat->'permissions'->'projects'
                ) = 'array'
        """
    )

    # OIDC Caveats were not emitting the permissions caveat correctly, so we'll
    # turn them into an empty array.
    op.execute(
        """ UPDATE macaroons
            SET caveats = jsonb_build_array()
            WHERE
                caveats IS NULL
                AND oidc_publisher_id IS NOT NULL
        """
    )

    # Set our column to not nullable
    op.alter_column(
        "macaroons", "caveats", server_default=sa.text("'{}'"), nullable=False
    )


def downgrade():
    op.drop_column("macaroons", "caveats")
