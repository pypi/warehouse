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
Fully deprecate legacy distribution types

Revision ID: b265ed9eeb8a
Revises: c4cb2d15dada
Create Date: 2020-03-12 17:51:08.447903
"""

from alembic import op

revision = "b265ed9eeb8a"
down_revision = "c4cb2d15dada"


def upgrade():
    op.drop_column("projects", "allow_legacy_files")


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
