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
Add a column for denormalizing Release.is_prerelease

Revision ID: b0dbcd2f5c77
Revises: 8bee9c119e41
Create Date: 2022-06-27 17:19:00.117464
"""

import sqlalchemy as sa

from alembic import op

revision = "b0dbcd2f5c77"
down_revision = "1e61006a47c2"


def upgrade():
    op.add_column("releases", sa.Column("is_prerelease", sa.Boolean(), nullable=True))

    op.execute(
        """ CREATE OR REPLACE FUNCTION maintain_releases_is_prerelease()
            RETURNS TRIGGER AS $$
                BEGIN
                    NEW.is_prerelease :=  pep440_is_prerelease(NEW.version);
                    RETURN NEW;
                END;
            $$
            LANGUAGE plpgsql
        """
    )

    op.execute(
        """ CREATE TRIGGER releases_update_is_prerelease
            BEFORE INSERT OR UPDATE OF version ON releases
            FOR EACH ROW
            EXECUTE PROCEDURE maintain_releases_is_prerelease()
        """
    )


def downgrade():
    op.drop_column("releases", "is_prerelease")
