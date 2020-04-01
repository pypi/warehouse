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
Drop denormalized normalized_name field

Revision ID: 28a7e805fd0
Revises: 91508cc5c2
Create Date: 2015-04-05 00:45:54.649441
"""

from alembic import op

revision = "28a7e805fd0"
down_revision = "91508cc5c2"


def upgrade():
    op.drop_column("packages", "normalized_name")


def downgrade():
    raise RuntimeError("Cannot downgrade past revision: {!r}".format(revision))
