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
from warehouse.packaging.models import Description, Project
from warehouse.packaging.tasks import compute_trending, update_description_html
from warehouse.utils import readme

from ...common.db.packaging import DescriptionFactory, ProjectFactory


class TestComputeTrending:
    @pytest.mark.parametrize("with_purges", [True, False])
    def test_computes_trending(self, db_request, with_purges):
        projects = [
            ProjectFactory.create(zscore=1 if not i else None) for i in range(3)
        ]

        results = iter(
            [
                Row(
                    (projects[1].normalized_name, 2, 3),
                    {"project": 0, "zscore": 1, "downloads_last_30_days": 2},
                ),
                Row(
                    (projects[2].normalized_name, -1, 6),
                    {"project": 0, "zscore": 1, "downloads_last_30_days": 2},
                ),
            ]
        )
        query = pretend.stub(result=pretend.call_recorder(lambda *a, **kw: results))
        bigquery = pretend.stub(query=pretend.call_recorder(lambda q: query))

        cacher = pretend.stub(purge=pretend.call_recorder(lambda keys: None))

        def find_service(iface=None, name=None):
            if iface is None and name == "gcloud.bigquery":
                return bigquery

            if with_purges and issubclass(iface, IOriginCache):
                return cacher

            raise LookupError

        db_request.find_service = find_service
        db_request.registry.settings = {
            "warehouse.trending_table": "example.pypi.downloads*"
        }

        compute_trending(db_request)

        assert bigquery.query.calls == [
            pretend.call(
                """ SELECT project,
                   SUM(downloads) as downloads_last_30_days,
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
        """
            )
        ]
        assert query.result.calls == [pretend.call()]
        assert cacher.purge.calls == (
            [pretend.call(["trending"])] if with_purges else []
        )

        results = {
            name: (zscore, downloads)
            for name, zscore, downloads in db_request.db.query(
                Project.name, Project.zscore, Project.downloads_last_30_days
            )
        }

        assert results == {
            projects[0].name: (None, None),
            projects[1].name: (2, 3),
            projects[2].name: (-1, 6),
        }


def test_update_description_html(monkeypatch, db_request):
    current_version = "24.0"
    previous_version = "23.0"

    monkeypatch.setattr(readme, "renderer_version", lambda: current_version)

    descriptions = [
        DescriptionFactory.create(html="rendered", rendered_by=current_version),
        DescriptionFactory.create(html="not this one", rendered_by=previous_version),
        DescriptionFactory.create(html="", rendered_by=""),  # Initial migration state
    ]

    update_description_html(db_request)

    assert set(
        db_request.db.query(
            Description.raw, Description.html, Description.rendered_by
        ).all()
    ) == {
        (descriptions[0].raw, "rendered", current_version),
        (descriptions[1].raw, readme.render(descriptions[1].raw), current_version),
        (descriptions[2].raw, readme.render(descriptions[2].raw), current_version),
    }
