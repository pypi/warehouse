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
Default hosting mode to pypi-only

Revision ID: 10cb17aea73
Revises: 41abd35caa3
Create Date: 2015-09-03 01:18:55.288971
"""

from alembic import op

revision = "10cb17aea73"
down_revision = "41abd35caa3"


def upgrade():
    op.alter_column(
        "packages",
        "hosting_mode",
        server_default="pypi-only",
        existing_server_default="pypi-explicit",
    )


def downgrade():
    op.alter_column(
        "packages",
        "hosting_mode",
        server_default="pypi-explicit",
        existing_server_default="pypi-only",
    )
