# Copyright 2013 Donald Stufft
#
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
add current_serial and trigger for package journal

Revision ID: 55b028ee498d
Revises: 55eda9672691
Create Date: 2014-02-09 11:52:39.756097
"""
from __future__ import absolute_import, division, print_function

# revision identifiers, used by Alembic.
revision = '55b028ee498d'
down_revision = '55eda9672691'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.add_column(
        "packages",
        sa.Column("current_serial", sa.INTEGER, nullable=True),
    )
    op.execute("""
        CREATE OR REPLACE FUNCTION update_packages_current_serial() RETURNS TRIGGER
        AS $journals$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                  UPDATE packages
                  SET    current_serial = (SELECT MAX(id) FROM journals WHERE name = OLD.name);
                ELSE
                  UPDATE packages
                  SET    current_serial = (SELECT MAX(id) FROM journals WHERE name = NEW.name);
                END IF;
                RETURN NULL;
            END;
        $journals$
        LANGUAGE 'plpgsql';
    """)
    op.execute("""
        CREATE TRIGGER update_packages_current_serial
        AFTER UPDATE OR INSERT OR DELETE ON journals
        FOR EACH ROW
        EXECUTE PROCEDURE update_packages_current_serial();
    """)
    op.execute("""
        UPDATE packages
        SET current_serial = (SELECT MAX(id) FROM journals WHERE name = packages.name)
        WHERE current_serial IS NULL;
    """)

def downgrade():
   op.execute("""
       DROP TRIGGER update_packages_current_serial ON journals;
   """)
   op.execute("""
       DROP FUNCTION update_packages_current_serial();
   """)
   op.drop_column(
       "packages", "current_serial"
   )
