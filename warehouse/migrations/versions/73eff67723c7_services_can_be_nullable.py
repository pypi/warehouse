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
Services can be nullable

Revision ID: 73eff67723c7
Revises: 752389dc7d00
Create Date: 2021-05-11 14:37:53.938864
"""

from alembic import op
import sqlalchemy as sa


revision = '73eff67723c7'
down_revision = '752389dc7d00'

# Note: It is VERY important to ensure that a migration does not lock for a
#       long period of time and to ensure that each individual migration does
#       not break compatibility with the *previous* version of the code base.
#       This is because the migrations will be ran automatically as part of the
#       deployment process, but while the previous version of the code is still
#       up and running. Thus backwards incompatible changes must be broken up
#       over multiple migrations inside of multiple pull requests in order to
#       phase them in over multiple deploys.

def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('sponsors', 'service',
               existing_type=sa.VARCHAR(),
               nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('sponsors', 'service',
               existing_type=sa.VARCHAR(),
               nullable=False)
    # ### end Alembic commands ###
