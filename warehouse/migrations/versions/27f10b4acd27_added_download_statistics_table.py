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
Added download_statistics table

Revision ID: 27f10b4acd27
Revises: 23515b7500af
Create Date: 2014-01-01 14:20:04.899624
"""
from __future__ import absolute_import, division, print_function

# revision identifiers, used by Alembic.
revision = '27f10b4acd27'
down_revision = '23515b7500af'

from alembic import op

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import func


def upgrade():
    op.create_table('downloads',
        sa.Column(
            'id',
            postgresql.UUID(),
            server_default=func.uuid_generate_v4(),
            nullable=False
        ),
        sa.Column('package_name', sa.UnicodeText(), nullable=False),
        sa.Column('package_version', sa.UnicodeText(), nullable=True),
        sa.Column(
            'distribution_type',
            sa.Enum(
                u'sdist',
                u'wheel',
                u'exe',
                u'egg',
                u'msi',
                name='distribution_type'
            ),
            nullable=True
        ),
        sa.Column(
            'python_type',
            sa.Enum(
                u'cpython',
                u'pypy',
                u'jython',
                u'ironpython',
                name='python_type'
            ),
            nullable=True
        ),
        sa.Column('python_release', sa.Text(), nullable=True),
        sa.Column('python_version', sa.Text(), nullable=True),
        sa.Column(
            'installer_type',
            sa.Enum(
                u'browser',
                u'pip',
                u'setuptools',
                u'distribute',
                u'bandersnatch',
                u'z3c.pypimirror',
                u'pep381client',
                name='installer_type'
            ),
            nullable=True
        ),
        sa.Column('installer_version', sa.Text(), nullable=True),
        sa.Column('operating_system', sa.Text(), nullable=True),
        sa.Column('operating_system_version', sa.Text(), nullable=True),
        sa.Column('download_time', sa.DateTime(), nullable=False),
        sa.Column('raw_user_agent', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('downloads')
