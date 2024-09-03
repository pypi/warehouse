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
Rollback attestation migration

Revision ID: 7ca0f1f5e7b3
Revises: 7f0c9f105f44
Create Date: 2024-08-21 19:52:40.084048
"""


from alembic import op

revision = "7ca0f1f5e7b3"
down_revision = "7f0c9f105f44"


def upgrade():
    op.drop_table("attestation")


def downgrade():
    pass
