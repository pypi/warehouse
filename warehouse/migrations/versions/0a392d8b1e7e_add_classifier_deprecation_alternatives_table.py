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
Add classification_deprecation_alternatives table

Revision ID: 0a392d8b1e7e
Revises: e82c3a017d60
Create Date: 2018-10-28 11:30:56.629863
"""

from alembic import op
import sqlalchemy as sa


revision = "0a392d8b1e7e"
down_revision = "e82c3a017d60"


def upgrade():
    op.create_table(
        "classification_deprecation_alternatives",
        sa.Column("deprecated_classifier_id", sa.Integer(), nullable=True),
        sa.Column("alternative_classifier_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["alternative_classifier_id"],
            ["trove_classifiers.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["deprecated_classifier_id"],
            ["trove_classifiers.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
    )


def downgrade():
    op.drop_table("classification_deprecation_alternatives")
