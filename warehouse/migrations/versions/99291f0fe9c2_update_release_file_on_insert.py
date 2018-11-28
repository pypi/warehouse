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

The release.requires_python and release_files.requires_python can be out of
sync if a file is uploaded after the release has been created. It's
requires_python field will stay empty.

We need to :
 - Fix potentially existing mistakes
 - Create a trigger that ensure consistency

Revision ID: 99291f0fe9c2
Revises: e7b09b5c089d
Create Date: 2016-12-02 00:58:53.109880
"""

from alembic import op

revision = "99291f0fe9c2"
down_revision = "e7b09b5c089d"


def upgrade():

    op.execute(
        """ UPDATE release_files
            SET requires_python = releases.requires_python
            FROM releases
            WHERE
                release_files.name=releases.name
                AND release_files.version=releases.version;
        """
    )

    # Establish a trigger such that on INSERT on release_files.
    # The requires_python value is no supposed to be set directly here
    # and UPDATES of the `releases` table already propagate.
    # Also triggering on UPDATE might create a recursion.
    op.execute(
        """ CREATE TRIGGER release_files_requires_python
              AFTER INSERT ON release_files
              FOR EACH ROW
                  EXECUTE PROCEDURE update_release_files_requires_python();
        """
    )


def downgrade():
    op.execute("DROP TRIGGER release_files_requires_python ON release_files")
