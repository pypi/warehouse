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
Disable legacy file types unless a project has used them previously

Revision ID: f404a67e0370
Revises: b8fda0d7fbb5
Create Date: 2016-12-17 02:58:55.328035
"""

from alembic import op

revision = "f404a67e0370"
down_revision = "b8fda0d7fbb5"


def upgrade():
    op.execute(
        r""" UPDATE packages
            SET allow_legacy_files = 'f'
            WHERE name NOT IN (
                SELECT DISTINCT ON (packages.name) packages.name
                FROM packages, release_files
                WHERE packages.name = release_files.name
                    AND (
                        filename !~* '.+?\.(tar\.gz|zip|whl|egg)$'
                        OR packagetype NOT IN (
                            'sdist',
                            'bdist_wheel',
                            'bdist_egg'
                        )
                    )
            )
        """
    )


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
