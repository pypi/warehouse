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
Add a sitemap_bucket column to User

Revision ID: 116be7c87e1
Revises: 5345b1bc8b9
Create Date: 2015-09-06 20:28:24.073366
"""

import sqlalchemy as sa

from alembic import op

revision = "116be7c87e1"
down_revision = "5345b1bc8b9"


def upgrade():
    # We need to add the column as nullable at first, because we need to
    # backfill our data.
    op.add_column(
        "accounts_user", sa.Column("sitemap_bucket", sa.Text(), nullable=True)
    )

    op.execute(
        """
        UPDATE accounts_user
        SET sitemap_bucket = sitemap_bucket(username)
        WHERE sitemap_bucket IS NULL
        """
    )

    # Now that data has been backfilled, we'll set nullable to False.
    op.alter_column("accounts_user", "sitemap_bucket", nullable=False)

    op.execute(
        """ CREATE OR REPLACE FUNCTION maintain_accounts_user_sitemap_bucket()
            RETURNS TRIGGER AS $$
                BEGIN
                    NEW.sitemap_bucket := sitemap_bucket(NEW.username);
                    RETURN NEW;
                END;
            $$
            LANGUAGE plpgsql
        """
    )

    # Finally, add the trigger which will keep the sitemap_bucket column
    # populated.
    op.execute(
        """ CREATE TRIGGER accounts_user_update_sitemap_bucket
            BEFORE INSERT OR UPDATE OF username ON accounts_user
            FOR EACH ROW
            EXECUTE PROCEDURE maintain_accounts_user_sitemap_bucket()
        """
    )


def downgrade():
    op.drop_column("accounts_user", "sitemap_bucket")
