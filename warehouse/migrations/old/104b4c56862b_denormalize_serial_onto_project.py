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
Denormalize serial onto project

Revision ID: 104b4c56862b
Revises: fb3278418206
Create Date: 2016-05-04 21:47:04.133779
"""

import sqlalchemy as sa

from alembic import op

revision = "104b4c56862b"
down_revision = "fb3278418206"


def upgrade():
    # Make sure that no new serials can be added while we're working on these
    # tables.
    op.execute("LOCK TABLE packages IN EXCLUSIVE MODE")
    op.execute("LOCK TABLE journals IN EXCLUSIVE MODE")

    op.add_column(
        "packages",
        sa.Column(
            "last_serial", sa.Integer(), nullable=True, server_default=sa.text("0")
        ),
    )

    # Set packages.last_serial for each package to the current maximum serial
    # as computed by the journals table.
    op.execute(
        """ UPDATE packages
            SET last_serial = j.last_serial
            FROM (
                SELECT name,
                       max(id) as last_serial
                FROM journals
                GROUP BY name
            ) as j
            WHERE j.name = packages.name
        """
    )

    # Now that data has been backfilled, we'll set nullable to False.
    op.alter_column("packages", "last_serial", nullable=False)

    # Setup a trigger function that will ensure that on INSERT/UPDATE/DELETE we
    # populate the packages.last_serial attribute with the new serial number.
    # 113359
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

                UPDATE packages
                SET last_serial = j.last_serial
                FROM (
                    SELECT max(id) as last_serial
                    FROM journals
                    WHERE journals.name = targeted_name
                ) as j
                WHERE packages.name = targeted_name;

                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """ CREATE TRIGGER update_project_last_serial
            AFTER INSERT OR UPDATE OR DELETE ON journals
            FOR EACH ROW EXECUTE PROCEDURE maintain_project_last_serial();
        """
    )


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
