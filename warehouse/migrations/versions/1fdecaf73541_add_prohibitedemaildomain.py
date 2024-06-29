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
Add ProhibitedEmailDomain

Revision ID: 1fdecaf73541
Revises: 93a1ca43e356
Create Date: 2024-03-28 02:23:25.712347
"""

import sqlalchemy as sa

from alembic import op

revision = "1fdecaf73541"
down_revision = "93a1ca43e356"


def upgrade():
    op.create_table(
        "prohibited_email_domains",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("prohibited_by", sa.UUID(), nullable=True),
        sa.Column("comment", sa.String(), server_default="", nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["prohibited_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain"),
    )
    op.create_index(
        op.f("ix_prohibited_email_domains_prohibited_by"),
        "prohibited_email_domains",
        ["prohibited_by"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_prohibited_email_domains_prohibited_by"),
        table_name="prohibited_email_domains",
    )
    op.drop_table("prohibited_email_domains")
