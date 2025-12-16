# SPDX-License-Identifier: Apache-2.0
"""
Data migration for UserUniqueLogin.ip_address_id

Revision ID: be443e514e3e
Revises: df52c3746740
Create Date: 2025-12-02 17:32:29.770684
"""


import os

import sqlalchemy as sa

from alembic import op

revision = "be443e514e3e"
down_revision = "df52c3746740"


def _get_remaining_logins_to_update(conn):
    return conn.execute(
        sa.text("SELECT COUNT(*) FROM user_unique_logins WHERE ip_address_id IS NULL")
    ).scalar_one()


def _get_remaining_ips_to_insert(conn):
    return conn.execute(
        sa.text(
            """
SELECT COUNT(DISTINCT user_unique_logins.ip_address)
FROM user_unique_logins
LEFT JOIN ip_addresses ON user_unique_logins.ip_address::inet = ip_addresses.ip_address
WHERE ip_addresses.id IS NULL AND user_unique_logins.ip_address IS NOT NULL
"""
        )
    ).scalar_one()


def upgrade():
    op.execute("SET statement_timeout = 120000")
    op.execute("SET lock_timeout = 120000")

    op.create_index(
        "ix_user_unique_logins_ip_address_migration",
        "user_unique_logins",
        ["ip_address"],
        unique=False,
        if_not_exists=True,
    )

    bind = op.get_bind()
    batch_size = 1000
    salt = os.environ.get("WAREHOUSE_IP_SALT")

    while _get_remaining_ips_to_insert(bind) > 0:
        bind.execute(
            sa.text(
                f"""
INSERT INTO ip_addresses (ip_address, hashed_ip_address)
SELECT
    DISTINCT user_unique_logins.ip_address::inet,
    encode(
        digest(
            CONCAT(user_unique_logins.ip_address, '{salt}'),
            'sha256'
        ),
        'hex'
    )
FROM user_unique_logins
LEFT JOIN ip_addresses ON user_unique_logins.ip_address::inet = ip_addresses.ip_address
WHERE ip_addresses.id IS NULL AND user_unique_logins.ip_address IS NOT NULL
LIMIT :batch_size
"""
            ),
            {"batch_size": batch_size},
        )
        bind.commit()

    while _get_remaining_logins_to_update(bind) > 0:
        bind.execute(
            sa.text(
                """
UPDATE user_unique_logins
SET ip_address_id = ip_addresses.id
FROM ip_addresses
WHERE
    user_unique_logins.ip_address::inet = ip_addresses.ip_address AND
    user_unique_logins.ip_address_id IS NULL AND
    user_unique_logins.id IN (
        SELECT id
        FROM user_unique_logins
        WHERE ip_address_id IS NULL
        ORDER BY id
        LIMIT :batch_size
    )
"""
            ),
            {"batch_size": batch_size},
        )
        bind.commit()

    # Finally make the ip_address_id column non-nullable
    op.alter_column("user_unique_logins", "ip_address_id", nullable=False)

    op.drop_index(
        "ix_user_unique_logins_ip_address_migration",
        "user_unique_logins",
        if_exists=True,
    )


def downgrade():
    op.alter_column("user_unique_logins", "ip_address_id", nullable=True)
