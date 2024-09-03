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
rollback attestations again

Revision ID: dcf1e3986782
Revises: 4037669366ca
Create Date: 2024-09-03 18:04:17.149056
"""

from alembic import op

revision = "dcf1e3986782"
down_revision = "4037669366ca"


def upgrade():
    op.drop_table("attestation")


def downgrade():
    pass
