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
Remove users without an email or a project

Revision ID: f71770e7d9b3
Revises: 42e76a605cac
Create Date: 2018-08-11 04:04:50.931746
"""

from alembic import op


revision = "f71770e7d9b3"
down_revision = "42e76a605cac"


def upgrade():
    op.execute(
        """
        DELETE FROM accounts_user
        WHERE NOT EXISTS
            (SELECT 1
             FROM accounts_email
             WHERE accounts_email.user_id = accounts_user.id)
          AND (accounts_user.last_login < CURRENT_TIMESTAMP - interval '1' year
                OR accounts_user.last_login IS NULL)
          AND NOT EXISTS
            (SELECT 1
             FROM roles
             WHERE roles.user_name = accounts_user.username)
          AND NOT EXISTS
            (SELECT 1
             FROM journals
             WHERE journals.submitted_by = accounts_user.username)
        """
    )


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
