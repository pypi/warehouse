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
Use enums instead of text

Revision ID: 111d8fc0443
Revises: 5988e3e8d2e
Create Date: 2015-03-08 22:46:46.870190
"""

from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision = "111d8fc0443"
down_revision = "5988e3e8d2e"


def upgrade():
    package_type = ENUM(
        "bdist_dmg",
        "bdist_dumb",
        "bdist_egg",
        "bdist_msi",
        "bdist_rpm",
        "bdist_wheel",
        "bdist_wininst",
        "sdist",
        name="package_type",
        create_type=False,
    )
    package_type.create(op.get_bind(), checkfirst=False)

    op.execute(
        """ ALTER TABLE release_files
                ALTER COLUMN packagetype
                TYPE package_type
                USING packagetype::package_type
        """
    )


def downgrade():
    op.execute(
        """ ALTER TABLE release_files
                ALTER COLUMN packagetype
                TYPE text
        """
    )

    ENUM(name="package_type", create_type=False).drop(op.get_bind(), checkfirst=False)
