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
Remove the rego_otk table abd related index

Revision ID: 42e76a605cac
Revises: 895279cc4490
Create Date: 2018-08-03 23:45:11.301066
"""

from alembic import op

revision = "42e76a605cac"
down_revision = "895279cc4490"


def upgrade():
    op.drop_index("rego_otk_name_idx", table_name="rego_otk")
    op.drop_index("rego_otk_otk_idx", table_name="rego_otk")
    op.drop_table("rego_otk")


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
