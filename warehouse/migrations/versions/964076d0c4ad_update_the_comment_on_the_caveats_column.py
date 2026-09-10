# SPDX-License-Identifier: Apache-2.0
"""
Update the comment on the caveats column

Revision ID: 964076d0c4ad
Revises: 423ffda7411f
Create Date: 2026-08-08 14:29:44.710940
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "964076d0c4ad"
down_revision = "423ffda7411f"


def upgrade():
    op.alter_column(
        "macaroons",
        "caveats",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        comment=(
            "The list of system generated caveats for this Macaroon. Users can add "
            "additional caveats at any time without communicating those additional "
            "caveats to us, which would not be reflected in this data, and thus this "
            "if this field is used for authorization or authentication purposes, it "
            "MUST be used as additional caveats along with whatever caveats are "
            "attached to the Macaroon. Older Macaroons may be missing caveats as "
            "previously only the legacy permissions caveats were stored."
        ),
        existing_comment=(
            "The list of caveats that were attached to this Macaroon when we generated "
            "it. Users can add additional caveats at any time without communicating "
            "those additional caveats to us, which would not be reflected in this "
            "data, and thus this field must only be used for informational purposes "
            "and must not be used during the authorization or authentication process. "
            "Older Macaroons may be missing caveats as previously only the legacy "
            "permissions caveat were stored."
        ),
        existing_nullable=False,
        existing_server_default=sa.text("'{}'::jsonb"),
    )


def downgrade():
    op.alter_column(
        "macaroons",
        "caveats",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        comment=(
            "The list of caveats that were attached to this Macaroon when we generated "
            "it. Users can add additional caveats at any time without communicating "
            "those additional caveats to us, which would not be reflected in this "
            "data, and thus this field must only be used for informational purposes "
            "and must not be used during the authorization or authentication process. "
            "Older Macaroons may be missing caveats as previously only the legacy "
            "permissions caveat were stored."
        ),
        existing_comment=(
            "The list of system generated caveats for this Macaroon. Users can add "
            "additional caveats at any time without communicating those additional "
            "caveats to us, which would not be reflected in this data, and thus this "
            "if this field is used for authorization or authentication purposes, it "
            "MUST be used as additional caveats along with whatever caveats are "
            "attached to the Macaroon. Older Macaroons may be missing caveats as "
            "previously only the legacy permissions caveats were stored."
        ),
        existing_server_default=sa.text("'{}'::jsonb"),
    )
