# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Record when the password was set

Revision ID: 039f45e2dbf9
Revises: a65114e48d6f
Create Date: 2016-06-15 13:10:02.361621
"""

import sqlalchemy as sa

from alembic import op

revision = "039f45e2dbf9"
down_revision = "a65114e48d6f"


def upgrade():
    # Purposely add the column and then set the default in two distinct
    # operations. This will ensure that existing users still have a null value
    # for their password_date, but new users get one set to NOW().
    op.add_column(
        "accounts_user", sa.Column("password_date", sa.DateTime(), nullable=True)
    )
    op.alter_column("accounts_user", "password_date", server_default=sa.text("now()"))

    op.execute(
        """ CREATE FUNCTION update_password_date()
            RETURNS TRIGGER AS $$
                BEGIN
                    NEW.password_date = now();
                    RETURN NEW;
                END;
            $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """ CREATE TRIGGER update_user_password_date
            BEFORE UPDATE OF password ON accounts_user
            FOR EACH ROW
            WHEN (OLD.password IS DISTINCT FROM NEW.password)
            EXECUTE PROCEDURE update_password_date()
        """
    )


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
