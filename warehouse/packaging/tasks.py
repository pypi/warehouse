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

from warehouse import tasks
from warehouse.cache.origin import IOriginCache
from warehouse.packaging.models import Project


@tasks.task(ignore_result=True, acks_late=True)
def compute_trending(request):
    bq = request.find_service(name="gcloud.bigquery")
    query = bq.run_sync_query(
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
        """.format(table=request.registry.settings["warehouse.trending_table"])
    )
    query.use_legacy_sql = False
    query.run()

    zscores = {}
    page_token = None
    while True:
        rows, total_rows, page_token = query.fetch_data(
            max_results=1000,
            page_token=page_token,
        )

        zscores.update(dict(rows))

        if not page_token:
            break

    # We're going to "reset" all of our zscores to a steady state where they
    # are all equal to ``None``. The next query will then set any that have a
    # value back to the expected value.
    (request.db.query(Project)
               .filter(Project.zscore != None)  # noqa
               .update({Project.zscore: None}))

    # We need to convert the normalized name that we get out of BigQuery and
    # turn it into the primary key of the Project object and construct a list
    # of primary key: new zscore, including a default of None if the item isn't
    # in the result set.
    query = request.db.query(Project.name, Project.normalized_name).all()
    to_update = [
        {"name": name, "zscore": zscores[normalized_name]}
        for name, normalized_name in query
        if normalized_name in zscores
    ]

    # Reflect out updated ZScores into the database.
    request.db.bulk_update_mappings(Project, to_update)

    # Trigger a purge of the trending surrogate key.
    try:
        cacher = request.find_service(IOriginCache)
    except ValueError:
        pass
    else:
        cacher.purge(["trending"])
