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
import uuid

from celery.exceptions import MaxRetriesExceededError

from warehouse import tasks
from warehouse.cache.origin import IOriginCache
from warehouse.packaging.models import Description, Project
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
    bind=True, ignore_result=True, acks_late=True, retry_backoff=15, retry_jitter=False
)
def update_distribution_database(task, request, file, form):
    """
    Updates release metadata to public BigQuery database
    """
    form_attrs = vars(form) if "__dict__" in form else form
    file_attrs = vars(file) if "__dict__" in file else file
    release = file_attrs["release"]
    release_attrs = vars(release) if "__dict__" in release else release

    bq = request.find_service(name="gcloud.bigquery")

    # Using the schema to populate the data allows us to automatically
    # set the values rather than assigning values individually
    def populate_data_using_schema(schema, row_data):

        for sch in schema:
            if sch.field_type == "RECORD":
                row_data[sch.name] = dict()
                populate_data_using_schema(sch.fields, row_data[sch.name])
            else:
                field_data = None

                # The order of data extraction below is determined based on the
                # classes that are most recently updated
                if sch.name in file_attrs:
                    field_data = file_attrs[sch.name]
                elif sch.name in form_attrs:
                    field_data = form_attrs[sch.name].data
                else:
                    field_data = release_attrs[sch.name]

                if isinstance(field_data, datetime.datetime):
                    field_data = field_data.isoformat()
                elif isinstance(field_data, uuid.UUID):
                    field_data = str(field_data)

                # Replace all empty objects to None will ensure
                # proper checks if a field is nullable or not
                if not isinstance(field_data, bool) and not field_data:
                    field_data = None

                row_data[sch.name] = field_data

    distribution_row_data = dict()
    table_name = request.registry.settings["warehouse.distribution_table"]
    populate_data_using_schema(bq.get_table(table_name).schema, distribution_row_data)

    # Convert the key value format so that it can be
    # plugged into a SQL query
    set_params = ""
    file_params = ""
    for key, value in distribution_row_data.items():
        if key != "files":
            if value is None:
                set_params += "{}=NULL,".format(key)
            elif isinstance(value, str):
                set_params += '{}="{}",'.format(key, value)
            else:
                set_params += "{}={},".format(key, value)
        else:
            for f_key, f_value in value.items():
                if f_value is None and f_key == "comment_text":
                    # We are doing this because BigQuery does not infer the type
                    #  of STRUCT field in the case of a NULL literal resulting in
                    #  an error forcing us to cast it to its assigned value
                    file_params += "CAST(NULL AS STRING) AS {},".format(f_key)
                elif isinstance(f_value, str):
                    file_params += '"{}" AS {},'.format(f_value, f_key)
                else:
                    file_params += "{} AS {},".format(f_value, f_key)
    file_params = file_params[:-1]

    try:
        updated_rows = bq.query(
            (
                "UPDATE {table} ".format(table=table_name)
                + "SET {set_params}".format(set_params=set_params)
                + "files=ARRAY_CONCAT"
                + "(files, [STRUCT({file_params})]) ".format(file_params=file_params)
                + "WHERE "
                + 'id="{release_id}";'.format(release_id=distribution_row_data["id"])
            )
        ).result()

        # No update on rows implies that its a new release
        # hence insert it into a new row
        if updated_rows is None or len(updated_rows) == 0:
            data_rows = [distribution_row_data]
            bq.insert_rows_json(table=table_name, json_rows=data_rows)
            # While there are expected to be error checks on the format of the
            # input data, the data is already pre-validated when this task is
            # initiated hence any error in the data format would be raised before
            # this point in code. The only check here is to ensure BigQuery is not down
    except Exception:
        try:
            task.retry(max_retries=5)
        except MaxRetriesExceededError:
            # TODO: Log this failed request for further analysis and possibly
            # propogate this to other tasks that fail silently
            pass
