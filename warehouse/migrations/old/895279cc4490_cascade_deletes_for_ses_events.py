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
Cascade deletes for SES Events and add an Index on the status.

Revision ID: 895279cc4490
Revises: b00323b3efd8
Create Date: 2018-08-03 21:21:23.695625
"""

from alembic import op

revision = "895279cc4490"
down_revision = "b00323b3efd8"


def upgrade():
    op.create_index(
        op.f("ix_ses_emails_status"), "ses_emails", ["status"], unique=False
    )
    op.drop_constraint("ses_events_email_id_fkey", "ses_events", type_="foreignkey")
    op.create_foreign_key(
        None,
        "ses_events",
        "ses_emails",
        ["email_id"],
        ["id"],
        ondelete="CASCADE",
        initially="DEFERRED",
        deferrable=True,
    )


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
