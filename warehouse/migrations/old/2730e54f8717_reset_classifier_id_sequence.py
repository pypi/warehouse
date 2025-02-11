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
Reset Classifier ID sequence

Revision ID: 2730e54f8717
Revises: 8fd3400c760f
Create Date: 2018-03-14 16:34:38.151300
"""

from alembic import op

revision = "2730e54f8717"
down_revision = "8fd3400c760f"


def upgrade():
    op.execute(
        """
        SELECT setval('trove_classifiers_id_seq', max(id))
        FROM trove_classifiers;
    """
    )


def downgrade():
    pass
