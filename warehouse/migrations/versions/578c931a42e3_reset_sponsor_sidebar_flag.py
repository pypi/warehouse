# SPDX-License-Identifier: Apache-2.0
"""
Reset the sponsor sidebar flag

The flag has not driven any rendering since the sidebar placement moved to
EthicalAds in 2021, so its values are stale. The hourly sync from pythondotorg
sets it again for the sponsors in the PyPI sidebar flight.

Revision ID: 578c931a42e3
Revises: b3c1d8e9f4a2
Create Date: 2026-10-22 10:42:35
"""

from alembic import op

revision = "578c931a42e3"
down_revision = "b3c1d8e9f4a2"


def upgrade():
    op.execute("UPDATE sponsors SET sidebar = false")


def downgrade():
    pass
