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
Add Index to Email.domain_last_checked

Revision ID: c8384ca429fc
Revises: f609b35e981b
Create Date: 2025-04-22 18:36:03.844860
"""

from alembic import op

revision = "c8384ca429fc"
down_revision = "f609b35e981b"


def upgrade():
    op.create_index(
        op.f("ix_user_emails_domain_last_checked"),
        "user_emails",
        ["domain_last_checked"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_user_emails_domain_last_checked"), table_name="user_emails")
