# Copyright 2013 Donald Stufft
#
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
Added devpi to installer_type enum

Revision ID: 55eda9672691
Revises: 27f10b4acd27
Create Date: 2014-01-05 19:30:18.451636
"""
from __future__ import absolute_import, division, print_function

# revision identifiers, used by Alembic.
revision = '55eda9672691'
down_revision = '27f10b4acd27'

from alembic import op


def upgrade():
    op.execute("COMMIT")  # See https://bitbucket.org/zzzeek/alembic/issue/123
    op.execute("""ALTER TYPE installer_type ADD VALUE 'devpi'""")


def downgrade():
    raise RuntimeError("This migration cannot be downgraded")
