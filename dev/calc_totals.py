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

from alembic import op
import sqlalchemy as sa
from sqlalchemy import func

from warehouse.packaging import Release, File, Project


def main():
    connection = op.get_bind()
    release_query = sa.select([Release.project_id, func.array_agg(Release.id)]).group_by(Release.project_id)
    for release in connection.execute(release_query):
        files_query = sa.select([func.sum(File.size)]).where(File.release_id.in_(release.array_agg_1))
        for files in connection.execute(files_query):
            connection.execute(
                sa.update(Project).values(total_size=files.sum_1).where(Project.id == release.project_id))


if __name__ == '__main__':
    main()
