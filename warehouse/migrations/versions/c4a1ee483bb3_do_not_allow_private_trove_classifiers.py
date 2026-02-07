# SPDX-License-Identifier: Apache-2.0
"""
Do not allow Private trove classifiers

Revision ID: c4a1ee483bb3
Revises: 3db69c05dd11
Create Date: 2019-02-17 20:01:54.314170
"""

from alembic import op

revision = "c4a1ee483bb3"
down_revision = "3db69c05dd11"


def upgrade():
    op.create_check_constraint(
        "ck_disallow_private_top_level_classifier",
        "trove_classifiers",
        "classifier not ilike 'private ::%'",
    )


def downgrade():
    op.drop_constraint("ck_disallow_private_top_level_classifier")
