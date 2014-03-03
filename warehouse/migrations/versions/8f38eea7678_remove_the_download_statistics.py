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
Remove the download statistics

Revision ID: 8f38eea7678
Revises: 4c8b2dd27587
Create Date: 2014-03-02 21:19:24.642402
"""
from __future__ import absolute_import, division, print_function

# revision identifiers, used by Alembic.
revision = '8f38eea7678'
down_revision = '4c8b2dd27587'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    op.drop_table('downloads')
    op.execute("DROP TYPE distribution_type")
    op.execute("DROP TYPE python_type")
    op.execute("DROP TYPE installer_type")


def downgrade():
    op.create_table(
        'downloads',
        sa.Column(
            'id',
            postgresql.UUID(),
            server_default=sa.text('uuid_generate_v4()'),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            'package_name',
            sa.TEXT(),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            'package_version',
            sa.TEXT(),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            'distribution_type',
            postgresql.ENUM(
                u'bdist_dmg',
                u'bdist_dumb',
                u'bdist_egg',
                u'bdist_msi',
                u'bdist_rpm',
                u'bdist_wheel',
                u'bdist_wininst',
                u'sdist',
                name='distribution_type',
            ),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            'python_type',
            postgresql.ENUM(
                u'cpython',
                u'pypy',
                u'jython',
                u'ironpython',
                name='python_type',
            ),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            'python_release',
            sa.TEXT(),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            'python_version',
            sa.TEXT(),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            'installer_type',
            postgresql.ENUM(
                u'browser',
                u'pip',
                u'setuptools',
                u'distribute',
                u'bandersnatch',
                u'z3c.pypimirror',
                u'pep381client',
                u'devpi',
                name='installer_type',
            ),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            'installer_version',
            sa.TEXT(),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            'operating_system',
            sa.TEXT(),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            'operating_system_version',
            sa.TEXT(),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            'download_time',
            postgresql.TIMESTAMP(),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            'raw_user_agent',
            sa.TEXT(),
            autoincrement=False,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=u'downloads_pkey'),
    )
