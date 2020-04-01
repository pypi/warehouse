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
Remove the description_html column

Revision ID: 41e9207fbe5
Revises: 49b93c346db
Create Date: 2015-06-03 19:44:43.269987
"""

from alembic import op

revision = "41e9207fbe5"
down_revision = "49b93c346db"


def upgrade():
    op.drop_column("releases", "description_html")


def downgrade():
    raise RuntimeError("Cannot downgrade past {!r}".format(revision))
