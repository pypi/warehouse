# SPDX-License-Identifier: Apache-2.0
"""
Rename tables

Revision ID: 06bfbc92f67d
Revises: eeb23d9b4d00
Create Date: 2018-11-06 04:36:58.531272
"""

from alembic import op

revision = "06bfbc92f67d"
down_revision = "e612a92c1017"


def upgrade():
    # The new verbiage in Warehouse is to call these things packages, but this table
    # name was inherited from legacy PyPI.
    op.rename_table("packages", "projects")
    op.execute("ALTER TABLE projects RENAME CONSTRAINT packages_pkey TO projects_pkey")
    op.execute(
        """
        ALTER TABLE projects
            RENAME CONSTRAINT packages_valid_name
            TO projects_valid_name
        """
    )
    op.execute(
        """ CREATE OR REPLACE FUNCTION maintain_project_last_serial()
            RETURNS TRIGGER AS $$
            DECLARE
                targeted_name text;
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    targeted_name := NEW.name;
                ELSEIF TG_OP = 'UPDATE' THEN
                    targeted_name := NEW.name;
                ELSIF TG_OP = 'DELETE' THEN
                    targeted_name := OLD.name;
                END IF;

                UPDATE projects
                SET last_serial = j.last_serial
                FROM (
                    SELECT max(id) as last_serial
                    FROM journals
                    WHERE journals.name = targeted_name
                ) as j
                WHERE projects.name = targeted_name;

                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "UPDATE row_counts SET table_name = 'projects' WHERE table_name = 'packages'"
    )

    # We took the name of these tables from a failed Django port, the new names are
    # cleaner and fit the overall "theme" of our table names better.
    op.rename_table("accounts_user", "users")
    op.execute("ALTER TABLE users RENAME CONSTRAINT accounts_user_pkey TO users_pkey")
    op.execute(
        """
        ALTER TABLE users
            RENAME CONSTRAINT accounts_user_username_key
            TO users_username_key
        """
    )
    op.execute(
        """
        ALTER TABLE users
            RENAME CONSTRAINT accounts_user_valid_username
            TO users_valid_username
        """
    )
    op.execute(
        """
        ALTER TABLE users
            RENAME CONSTRAINT packages_valid_name
            TO users_valid_username_length
        """
    )
    op.execute(
        "UPDATE row_counts SET table_name = 'users' WHERE table_name = 'accounts_user'"
    )

    op.rename_table("accounts_email", "user_emails")
    op.execute(
        """
        ALTER TABLE user_emails
            RENAME CONSTRAINT accounts_email_pkey
            TO user_emails_pkey
        """
    )
    op.execute(
        """
        ALTER TABLE user_emails
            RENAME CONSTRAINT accounts_email_email_key
            TO user_emails_email_key
        """
    )
    op.execute(
        """
        ALTER TABLE user_emails
            RENAME CONSTRAINT accounts_email_user_id_fkey
            TO user_emails_user_id_fkey
        """
    )
    op.execute("ALTER INDEX accounts_email_user_id RENAME TO user_emails_user_id")

    # While the admin prefix on these tables is useful to let us know they are specific
    # to the admins, the warehouse prefix is not. All of these tables in this database
    # are for Warehouse.
    op.rename_table("warehouse_admin_flag", "admin_flags")
    op.execute(
        """
        ALTER TABLE admin_flags
            RENAME CONSTRAINT warehouse_admin_flag_pkey
            TO admin_flags_pkey
        """
    )

    op.rename_table("warehouse_admin_squat", "admin_squats")
    op.execute(
        """
        ALTER TABLE admin_squats
            RENAME CONSTRAINT warehouse_admin_squat_pkey
            TO admin_squats_pkey
        """
    )
    op.execute(
        """
        ALTER TABLE admin_squats
            RENAME CONSTRAINT warehouse_admin_squat_squattee_id_fkey
            TO admin_squats_squattee_id_fkey
        """
    )
    op.execute(
        """
        ALTER TABLE admin_squats
            RENAME CONSTRAINT warehouse_admin_squat_squatter_id_fkey
            TO admin_squats_squatter_id_fkey
        """
    )


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
