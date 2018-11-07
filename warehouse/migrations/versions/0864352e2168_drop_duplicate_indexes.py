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
Drop duplicate indexes

Revision ID: 0864352e2168
Revises: 6a6eb0a95603
Create Date: 2018-08-15 20:27:08.429077
"""

from alembic import op


revision = "0864352e2168"
down_revision = "6a6eb0a95603"


def upgrade():
    # This is an exact duplicate of the accounts_email_email_key index, minus the unique
    # constraint.
    op.drop_index("accounts_email_email_like", table_name="accounts_email")
    # This is an exact duplicate of the journals_pkey index, minus the primary key
    # constraint.
    op.drop_index("journals_id_idx", table_name="journals")
    # This is an exact duplicate of the trove_classifiers_classifier_key index, minus
    # the unique constraint.
    op.drop_index("trove_class_class_idx", table_name="trove_classifiers")
    # This is an exact duplicate of the trove_classifiers_pkey index, minus the primary
    # key constraint.
    op.drop_index("trove_class_id_idx", table_name="trove_classifiers")


def downgrade():
    op.create_index("trove_class_id_idx", "trove_classifiers", ["id"], unique=False)
    op.create_index(
        "trove_class_class_idx", "trove_classifiers", ["classifier"], unique=False
    )
    op.create_index("journals_id_idx", "journals", ["id"], unique=False)
    op.create_index(
        "accounts_email_email_like", "accounts_email", ["email"], unique=False
    )
