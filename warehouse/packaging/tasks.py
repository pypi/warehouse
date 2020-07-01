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

import datetime

from warehouse import tasks
from warehouse.cache.origin import IOriginCache
from warehouse.packaging.models import Description, File, Project, Release
from warehouse.utils import readme


@tasks.task(ignore_result=True, acks_late=True)
def compute_trending(request):
    bq = request.find_service(name="gcloud.bigquery")
    query = bq.query(
        """ SELECT project,
                   IF(
                        STDDEV(downloads) > 0,
                        (todays_downloads - AVG(downloads))/STDDEV(downloads),
                        NULL
                    ) as zscore
            FROM (
                SELECT project,
                       date,
                       downloads,
                       FIRST_VALUE(downloads) OVER (
                            PARTITION BY project
                            ORDER BY DATE DESC
                            ROWS BETWEEN UNBOUNDED PRECEDING
                                AND UNBOUNDED FOLLOWING
                        ) as todays_downloads
                FROM (
                    SELECT file.project as project,
                           DATE(timestamp) AS date,
                           COUNT(*) as downloads
                    FROM `{table}`
                    WHERE _TABLE_SUFFIX BETWEEN
                        FORMAT_DATE(
                            "%Y%m%d",
                            DATE_ADD(CURRENT_DATE(), INTERVAL -31 day))
                        AND
                        FORMAT_DATE(
                            "%Y%m%d",
                            DATE_ADD(CURRENT_DATE(), INTERVAL -1 day))
                    GROUP BY file.project, date
                )
            )
            GROUP BY project, todays_downloads
            HAVING SUM(downloads) >= 5000
            ORDER BY zscore DESC
        """.format(
            table=request.registry.settings["warehouse.trending_table"]
        )
    )

    zscores = {}
    for row in query.result():
        row = dict(row)
        zscores[row["project"]] = row["zscore"]

    # We're going to "reset" all of our zscores to a steady state where they
    # are all equal to ``None``. The next query will then set any that have a
    # value back to the expected value.
    (
        request.db.query(Project)
        .filter(Project.zscore != None)  # noqa
        .update({Project.zscore: None})
    )

    # We need to convert the normalized name that we get out of BigQuery and
    # turn it into the primary key of the Project object and construct a list
    # of primary key: new zscore, including a default of None if the item isn't
    # in the result set.
    query = request.db.query(Project.id, Project.normalized_name).all()
    to_update = [
        {"id": id, "zscore": zscores[normalized_name]}
        for id, normalized_name in query
        if normalized_name in zscores
    ]

    # Reflect out updated ZScores into the database.
    request.db.bulk_update_mappings(Project, to_update)

    # Trigger a purge of the trending surrogate key.
    try:
        cacher = request.find_service(IOriginCache)
    except LookupError:
        pass
    else:
        cacher.purge(["trending"])


@tasks.task(ignore_result=True, acks_late=True)
def update_description_html(request):
    renderer_version = readme.renderer_version()

    descriptions = (
        request.db.query(Description)
        .filter(Description.rendered_by != renderer_version)
        .yield_per(100)
        .limit(500)
    )

    for description in descriptions:
        description.html = readme.render(description.raw, description.content_type)
        description.rendered_by = renderer_version


@tasks.task(
    bind=True,
    ignore_result=True,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=15,
    retry_jitter=False,
    max_retries=5,
)
def update_bigquery_release_files(task, request, file, form):
    """
    Adds release file metadata to public BigQuery database
    """
    bq = request.find_service(name="gcloud.bigquery")

    table_name = request.registry.settings["warehouse.release_files_table"]
    table_schema = bq.get_table(table_name).schema

    # Using the schema to populate the data allows us to automatically
    # set the values to their respective fields rather than assigning
    # values individually
    json_rows = dict()
    for sch in table_schema:
        # The order of data extraction below is determined based on the
        # classes that are most recently updated
        if hasattr(file, sch.name):
            field_data = getattr(file, sch.name)
        else:
            field_data = form[sch.name].data

        if isinstance(field_data, datetime.datetime):
            field_data = field_data.isoformat()

        # Replace all empty objects to None will ensure
        # proper checks if a field is nullable or not
        if not isinstance(field_data, bool) and not field_data:
            field_data = None

        if field_data is None and sch.mode == "REPEATED":
            json_rows[sch.name] = []
        else:
            json_rows[sch.name] = field_data
    json_rows = [json_rows]

    bq.insert_rows_json(table=table_name, json_rows=json_rows)


@tasks.task(ignore_result=True, acks_late=True)
def sync_bigquery_release_files(request):
    bq = request.find_service(name="gcloud.bigquery")
    table_name = request.registry.settings["warehouse.release_files_table"]
    table_schema = bq.get_table(table_name).schema

    db_release_files = request.db.query(File).all()
    db_file_digests = [file.md5_digest for file in db_release_files]

    bq_file_digests = bq.query(f"SELECT md5_digest FROM {table_name}").result()
    bq_file_digests = [row.get("md5_digest") for row in bq_file_digests]

    md5_diff_list = list(set(db_file_digests) - set(bq_file_digests))[:1000]

    release_files = (
        request.db.query(File)
        .join(Release, Release.id == File.release_id)
        .filter(File.md5_digest.in_(md5_diff_list))
        .all()
    )

    # Using the schema to populate the data allows us to automatically
    # set the values to their respective fields rather than assigning
    # values individually
    def populate_data_using_schema(file):
        release = file.release
        project = release.project

        row_data = dict()
        for sch in table_schema:
            # The order of data extraction below is determined based on the
            # classes that are most recently updated
            if hasattr(file, sch.name):
                field_data = getattr(file, sch.name)
            elif hasattr(release, sch.name) and sch.name == "description":
                field_data = getattr(release, sch.name).raw
            elif sch.name == "description_content_type":
                field_data = getattr(release, "description").content_type
            elif hasattr(release, sch.name):
                field_data = getattr(release, sch.name)
            elif hasattr(project, sch.name):
                field_data = getattr(project, sch.name)
            else:
                field_data = None

            if isinstance(field_data, datetime.datetime):
                field_data = field_data.isoformat()

            # Replace all empty objects to None will ensure
            # proper checks if a field is nullable or not
            if not isinstance(field_data, bool) and not field_data:
                field_data = None

            if field_data is None and sch.mode == "REPEATED":
                row_data[sch.name] = []
            else:
                row_data[sch.name] = field_data
        return row_data

    json_rows = [populate_data_using_schema(file) for file in release_files]

    bq.insert_rows_json(table=table_name, json_rows=json_rows)
