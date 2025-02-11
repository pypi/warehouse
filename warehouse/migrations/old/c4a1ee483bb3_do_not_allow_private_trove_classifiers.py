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
Do not allow Private trove classifiers

Revision ID: c4a1ee483bb3
Revises: 3db69c05dd11
Create Date: 2019-02-17 20:01:54.314170
"""

from alembic import op

revision = "c4a1ee483bb3"
down_revision = "3db69c05dd11"


def upgrade():
    op.create_check_constraint(
        "ck_disallow_private_top_level_classifier",
        "trove_classifiers",
        "classifier not ilike 'private ::%'",
    )


def downgrade():
    op.drop_constraint("ck_disallow_private_top_level_classifier")
