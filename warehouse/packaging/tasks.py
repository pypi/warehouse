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
from warehouse.classifiers.models import Classifier
from warehouse.packaging.models import (
    Dependency,
    Description,
    File,
    Project,
    Release,
    release_classifiers,
)
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

    # Using the schema to populate the data allows us to automatically
    # set the values to their respective fields rather than assigning
    # values individually
    def populate_data_using_schema(schema, row_data):

        for sch in schema:
            field_data = None

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
                row_data[sch.name] = []
            else:
                row_data[sch.name] = field_data

    distribution_row_data = dict()
    table_name = request.registry.settings["warehouse.release_files_table"]
    populate_data_using_schema(bq.get_table(table_name).schema, distribution_row_data)

    data_rows = [distribution_row_data]
    bq.insert_rows_json(table=table_name, json_rows=data_rows)


@tasks.task(ignore_result=True, acks_late=True)
def sync_bigquery_release_files(request):
    bq = request.find_service(name="gcloud.bigquery")
    table_name = request.registry.settings["warehouse.release_files_table"]
    table_schema = bq.get_table(table_name).schema

    db_release_files = (
        request.db.query(File).all()
    )
    db_file_digests = [file.md5_digest for file in db_release_files]

    bq_file_digests = bq.query(f"SELECT md5_digest FROM {table_name}").result()
    bq_file_digests = [row.get("md5_digest") for row in bq_file_digests]

    md5_diff_list = list(set(db_file_digests) - set(bq_file_digests))[:1000]

    release_files = (
        request.db.query(Release)
        .join(Project, Release.project_id == Project.id)
        .join(Description, Release.description_id == Description.id)
        .join(File, Release.id == File.release_id)
        .join(release_classifiers, Release.id == release_classifiers.release_id)
        .join(Classifier, release_classifiers.trove_id == Classifer.id)
        .join(Dependency, Release.id == Dependency.release_id)
        .filter(File.md5_digest.in_(md5_diff_list))
        .all()
    )

    rows_to_insert = parse_sql(release_files)

    # Parse dependencies before populating schema data
    dep_kind = {
        1: "requires",
        2: "provides",
        3: "obsoletes",
        4: "requires_dist",
        5: "provides_dist",
        6: "obsoletes_dist",
        7: "requires_external",
        8: "project_urls"
    }
    for i in range(len(release_files)):
        if release_files[i]['kind']:
            release_files[i][dep_kind[release_files[i]['kind']]] = release_files[i]['specifier']

    rows_to_insert = dict()
    for row in release_files:
        if (row['id'], row['filename']) in return_data:
            output_data = return_data[(row['id'], row['filename'])]
        else:
            output_data = dict()

        for sch in table_schema:
            field_data = None

            if sch.name in row:
                field_data = row[sch.name]

            if not isinstance(field_data, bool) and not field_data:
                field_data = None

            if sch.mode == "REPEATED":
                if not field_data is None:
                    if not sch.name in output_data or not output_data[sch.name]:
                        output_data[sch.name] = [field_data]
                    elif not field_data in output_data[sch.name]:
                        output_data[sch.name].append(field_data)
                elif field_data is None and not sch.name in output_data:
                    output_data[sch.name] = []
            else:
                output_data[sch.name] = field_data

        rows_to_insert[(row['id'], row['filename'])] = output_data

    rows_to_insert = [rows_to_insert[key] for key in rows_to_insert]

    bq.insert_rows_json(table=table_name, json_rows=rows_to_insert)
