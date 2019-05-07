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
