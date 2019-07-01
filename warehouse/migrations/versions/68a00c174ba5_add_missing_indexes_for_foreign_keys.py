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
add missing indexes for foreign keys

Revision ID: 68a00c174ba5
Revises: 42e76a605cac
Create Date: 2018-08-13 16:49:12.920887
"""

from alembic import op

revision = "68a00c174ba5"
down_revision = "42e76a605cac"


def upgrade():
    op.create_index(
        op.f("ix_blacklist_blacklisted_by"),
        "blacklist",
        ["blacklisted_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ses_events_email_id"), "ses_events", ["email_id"], unique=False
    )
    # CREATE INDEX CONCURRENTLY cannot happen inside a transaction. We'll close
    # our transaction here and issue the statement.
    op.execute("COMMIT")
    op.create_index(
        "journals_submitted_by_idx",
        "journals",
        ["submitted_by"],
        unique=False,
        postgresql_concurrently=True,
    )


def downgrade():
    op.drop_index("journals_submitted_by_idx", table_name="journals")
    op.drop_index(op.f("ix_ses_events_email_id"), table_name="ses_events")
    op.drop_index(op.f("ix_blacklist_blacklisted_by"), table_name="blacklist")
