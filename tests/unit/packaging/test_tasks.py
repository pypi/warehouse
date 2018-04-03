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

import pretend
import pytest

from google.cloud.bigquery import Row

from warehouse.cache.origin import IOriginCache
from warehouse.packaging.models import Project
from warehouse.packaging.tasks import compute_trending

from ...common.db.packaging import ProjectFactory


class TestComputeTrending:

    @pytest.mark.parametrize("with_purges", [True, False])
    def test_computes_trending(self, db_request, with_purges):
        projects = [
            ProjectFactory.create(zscore=1 if not i else None)
            for i in range(3)
        ]

        results = iter([
            Row(
                (projects[1].normalized_name, 2),
                {'project': 0, 'zscore': 1},
            ),
            Row(
                (projects[2].normalized_name, -1),
                {'project': 0, 'zscore': 1},
            ),
        ])
        query = pretend.stub(
            result=pretend.call_recorder(
                lambda *a, **kw: results,
            )
        )
        bigquery = pretend.stub(
            query=pretend.call_recorder(lambda q: query),
        )

        cacher = pretend.stub(purge=pretend.call_recorder(lambda keys: None))

        def find_service(iface=None, name=None):
            if iface is None and name == "gcloud.bigquery":
                return bigquery

            if with_purges and issubclass(iface, IOriginCache):
                return cacher

            raise ValueError

        db_request.find_service = find_service
        db_request.registry.settings = {
            "warehouse.trending_table": "example.pypi.downloads*",
        }

        compute_trending(db_request)

        assert bigquery.query.calls == [
            pretend.call(""" SELECT project,
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
                    FROM `example.pypi.downloads*`
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
        """),
        ]
        assert query.result.calls == [pretend.call()]
        assert (cacher.purge.calls ==
                ([pretend.call(["trending"])] if with_purges else []))

        results = dict(db_request.db.query(Project.name, Project.zscore).all())

        assert results == {
            projects[0].name: None,
            projects[1].name: 2,
            projects[2].name: -1,
        }
