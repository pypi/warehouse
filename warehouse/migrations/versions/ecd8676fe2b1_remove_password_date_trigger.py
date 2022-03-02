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
remove password_date trigger

Revision ID: ecd8676fe2b1
Revises: 19cf76d2d459
Create Date: 2022-03-02 16:17:32.228716
"""

from alembic import op


revision = 'ecd8676fe2b1'
down_revision = '19cf76d2d459'


def upgrade():
    op.execute(
        "DROP TRIGGER update_user_password_date ON users"
    )
    op.execute(
        "DROP FUNCTION update_password_date"
    )


def downgrade():
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
            BEFORE UPDATE OF password ON users
            FOR EACH ROW
            WHEN (OLD.password IS DISTINCT FROM NEW.password)
            EXECUTE PROCEDURE update_password_date()
        """
    )
