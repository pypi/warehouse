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
unique_org_names

Revision ID: 4f8982e60deb
Revises: 465f004c9562
Create Date: 2025-04-11 14:03:21.787409
"""


from alembic import op
from alembic_postgresql_enum import TableReference

revision = "4f8982e60deb"
down_revision = "465f004c9562"


def upgrade():
    op.create_unique_constraint(
        "_organization_name_catalog_normalized_name_uc",
        "organization_name_catalog",
        ["normalized_name"],
    )
    op.sync_enum_values(
        enum_schema="public",
        enum_name="organizationmembershipsize",
        new_values=["", "1", "2-5", "6-10", "11-25", "26-50", "51-100", "100+"],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="organization_applications",
                column_name="membership_size",
            )
        ],
        enum_values_to_rename=[],
    )


def downgrade():
    op.sync_enum_values(
        enum_schema="public",
        enum_name="organizationmembershipsize",
        new_values=["1", "2-5", "6-10", "11-25", "26-50", "51-100", "100+"],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="organization_applications",
                column_name="membership_size",
            )
        ],
        enum_values_to_rename=[],
    )
    op.drop_constraint(
        "_organization_name_catalog_normalized_name_uc",
        "organization_name_catalog",
        type_="unique",
    )
