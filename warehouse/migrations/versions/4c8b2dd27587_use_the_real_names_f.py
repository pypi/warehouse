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
Use the real names for distribution types

Revision ID: 4c8b2dd27587
Revises: 55eda9672691
Create Date: 2014-01-11 22:17:16.139038
"""
from __future__ import absolute_import, division, print_function

# revision identifiers, used by Alembic.
revision = '4c8b2dd27587'
down_revision = '55eda9672691'

from alembic import op


def upgrade():
    op.execute(
        """ ALTER TABLE downloads
            ALTER COLUMN distribution_type
                TYPE text USING distribution_type::text
        """
    )
    op.execute("DROP TYPE distribution_type")
    op.execute(
        """ UPDATE downloads
            SET distribution_type = 'bdist_egg'
            WHERE distribution_type = 'egg'
        """
    )
    op.execute(
        """ UPDATE downloads
            SET distribution_type = 'bdist_msi'
            WHERE distribution_type = 'msi'
        """
    )
    op.execute(
        """ UPDATE downloads
            SET distribution_type = 'bdist_wheel'
            WHERE distribution_type = 'wheel'
        """
    )
    op.execute(
        """ UPDATE downloads
            SET distribution_type = 'bdist_wininst'
            WHERE distribution_type = 'exe'
        """
    )
    op.execute(
        """ CREATE TYPE distribution_type AS ENUM
            (
                'bdist_dmg',
                'bdist_dumb',
                'bdist_egg',
                'bdist_msi',
                'bdist_rpm',
                'bdist_wheel',
                'bdist_wininst',
                'sdist'
            )
        """
    )
    op.execute(
        """ ALTER TABLE downloads
            ALTER COLUMN distribution_type
                TYPE distribution_type
                USING distribution_type::distribution_type
        """
    )


def downgrade():
    raise RuntimeError("This migration cannot be downgraded")
