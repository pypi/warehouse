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
Cascade deletes from Project/Release/File to Verdicts

Revision ID: f47d2f06c13e
Revises: 061ff3d24c22
Create Date: 2020-02-20 17:28:36.194480
"""

from alembic import op

revision = "f47d2f06c13e"
down_revision = "061ff3d24c22"


def upgrade():
    op.drop_constraint(
        "malware_verdicts_project_id_fkey", "malware_verdicts", type_="foreignkey"
    )
    op.drop_constraint(
        "malware_verdicts_release_id_fkey", "malware_verdicts", type_="foreignkey"
    )
    op.drop_constraint(
        "malware_verdicts_file_id_fkey", "malware_verdicts", type_="foreignkey"
    )
    op.create_foreign_key(
        "malware_verdicts_project_id_fkey",
        "malware_verdicts",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "malware_verdicts_release_id_fkey",
        "malware_verdicts",
        "releases",
        ["release_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "malware_verdicts_file_id_fkey",
        "malware_verdicts",
        "release_files",
        ["file_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(
        "malware_verdicts_file_id_fkey", "malware_verdicts", type_="foreignkey"
    )
    op.drop_constraint(
        "malware_verdicts_release_id_fkey", "malware_verdicts", type_="foreignkey"
    )
    op.drop_constraint(
        "malware_verdicts_project_id_fkey", "malware_verdicts", type_="foreignkey"
    )
    op.create_foreign_key(
        "malware_verdicts_file_id_fkey",
        "malware_verdicts",
        "release_files",
        ["file_id"],
        ["id"],
    )
    op.create_foreign_key(
        "malware_verdicts_release_id_fkey",
        "malware_verdicts",
        "releases",
        ["release_id"],
        ["id"],
    )
    op.create_foreign_key(
        "malware_verdicts_project_id_fkey",
        "malware_verdicts",
        "projects",
        ["project_id"],
        ["id"],
    )
