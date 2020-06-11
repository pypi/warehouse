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

from uuid import UUID

import pretend
import pytest

from celery.exceptions import MaxRetriesExceededError
from google.cloud.bigquery import Row, SchemaField
from wtforms import Field, Form, StringField

from warehouse.cache.origin import IOriginCache
from warehouse.packaging import tasks
from warehouse.packaging.models import Description, Project
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
                Row((projects[1].normalized_name, 2), {"project": 0, "zscore": 1}),
                Row((projects[2].normalized_name, -1), {"project": 0, "zscore": 1}),
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

        tasks.compute_trending(db_request)

        assert bigquery.query.calls == [
            pretend.call(
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

        results = dict(db_request.db.query(Project.name, Project.zscore).all())

        assert results == {
            projects[0].name: None,
            projects[1].name: 2,
            projects[2].name: -1,
        }


class TestUpdateDistributionDatabase:
    class ListField(Field):
        def process_formdata(self, valuelist):
            self.data = [v.strip() for v in valuelist if v.strip()]

    input_parameters = [
        (
            {
                "release": {
                    "maintainer": None,
                    "requires_python": None,
                    "maintainer_email": None,
                    "created": datetime.datetime(2020, 6, 11, 0, 19, 10, 875885),
                    "id": UUID("2e1fe167-8078-443e-b21d-07fd1abe5d56"),
                    "home_page": None,
                    "project_id": UUID("8e8d5a52-bb37-474a-8c2e-d5ec67001405"),
                    "description_id": UUID("7adffac0-eea4-41d2-91e6-15c5fa2d03f7"),
                    "_pypi_ordering": 0,
                    "license": None,
                    "version": "1.0",
                    "yanked": False,
                    "summary": None,
                    "yanked_reason": "",
                    "canonical_version": "1",
                    "keywords": None,
                    "uploader_id": UUID("3796ac62-3527-4041-be18-f369ae1b24e5"),
                    "author": None,
                    "platform": None,
                    "author_email": None,
                    "uploaded_via": None,
                    "download_url": None,
                    "files": True,
                },
                "filename": "OfDABTihRTmE-1.0.tar.gz",
                "python_version": "source",
                "packagetype": "sdist",
                "comment_text": "",
                "size": 192,
                "has_signature": False,
                "md5_digest": "7fcdcb15530ea82d2a5daf98a4997c57",
                "sha256_digest": (
                    "a983cbea389641f78541e25c14ab1a488ede2641119a5be807e94645c4f3d25d"
                ),
                "blake2_256_digest": (
                    "620f55b4f450c8a20a0a2aea447cc519ac33a7a7043759a8a03685cbac5f4871"
                ),
                "path": (
                    "62/0f/55b4f450c8a20a0a2aea447cc519ac33a7a704"
                    "3759a8a03685cbac5f4871/OfDABTihRTmE-1.0.tar.gz"
                ),
                "uploaded_via": "warehouse-tests/6.6.6",
            },
            {
                "metadata_version": StringField(default="1.2").bind(Form(), "test"),
                "name": StringField(default="OfDABTihRTmE").bind(Form(), "test"),
                "version": StringField(default="1.0").bind(Form(), "test"),
                "summary": StringField(default="").bind(Form(), "test"),
                "description": StringField(default="an example description").bind(
                    Form(), "test"
                ),
                "author": StringField(default="").bind(Form(), "test"),
                "description_content_type": StringField(default="").bind(Form(), "a"),
                "author_email": StringField(default="").bind(Form(), "test"),
                "maintainer": StringField(default="").bind(Form(), "test"),
                "maintainer_email": StringField(default="").bind(Form(), "test"),
                "license": StringField(default="").bind(Form(), "test"),
                "keywords": StringField(default="").bind(Form(), "test"),
                "classifiers": ListField(
                    default=["Environment :: Other Environment"]
                ).bind(Form(), "test"),
                "platform": StringField(default="").bind(Form(), "test"),
                "home_page": StringField(default="").bind(Form(), "test"),
                "download_url": StringField(default="").bind(Form(), "test"),
                "requires_python": StringField(default="").bind(Form(), "test"),
                "pyversion": StringField(default="source").bind(Form(), "test"),
                "filetype": StringField(default="sdist").bind(Form(), "test"),
                "comment": StringField(default="").bind(Form(), "test"),
                "md5_digest": StringField(
                    default="7fcdcb15530ea82d2a5daf98a4997c57"
                ).bind(Form(), "test"),
                "sha256_digest": StringField(
                    default=(
                        "a983cbea389641f78541e25c14ab1a488ede2641119a5be807e"
                        "94645c4f3d25d"
                    )
                ).bind(Form(), "test"),
                "blake2_256_digest": StringField(default="").bind(Form(), "test"),
                "requires": ListField(default=[]).bind(Form(), "test"),
                "provides": ListField(default=[]).bind(Form(), "test"),
                "obsoletes": ListField(default=[]).bind(Form(), "test"),
                "requires_dist": ListField(default=[]).bind(Form(), "test"),
                "provides_dist": ListField(default=[]).bind(Form(), "test"),
                "obsoletes_dist": ListField(default=[]).bind(Form(), "test"),
                "requires_external": ListField(default=[]).bind(Form(), "test"),
                "project_urls": ListField(default=[]).bind(Form(), "test"),
            },
            [
                SchemaField("id", "STRING", "REQUIRED"),
                SchemaField("metadata_version", "STRING", "REQUIRED"),
                SchemaField("project_id", "STRING", "REQUIRED"),
                SchemaField("name", "STRING", "REQUIRED"),
                SchemaField("version", "STRING", "REQUIRED"),
                SchemaField("summary", "STRING", "NULLABLE"),
                SchemaField("description_id", "STRING", "REQUIRED"),
                SchemaField("description", "STRING", "REQUIRED"),
                SchemaField("description_content_type", "STRING", "NULLABLE"),
                SchemaField("author", "STRING", "NULLABLE"),
                SchemaField("author_email", "STRING", "NULLABLE"),
                SchemaField("maintainer", "STRING", "NULLABLE"),
                SchemaField("maintainer_email", "STRING", "NULLABLE"),
                SchemaField("license", "STRING", "NULLABLE"),
                SchemaField("keywords", "STRING", "NULLABLE"),
                SchemaField("classifiers", "STRING", "REPEATED"),
                SchemaField("platform", "STRING", "REPEATED"),
                SchemaField("home_page", "STRING", "NULLABLE"),
                SchemaField("download_url", "STRING", "NULLABLE"),
                SchemaField("requires_python", "STRING", "NULLABLE"),
                SchemaField("requires", "STRING", "REPEATED"),
                SchemaField("provides", "STRING", "REPEATED"),
                SchemaField("obsoletes", "STRING", "REPEATED"),
                SchemaField("requires_dist", "STRING", "REPEATED"),
                SchemaField("provides_dist", "STRING", "REPEATED"),
                SchemaField("obsoletes_dist", "STRING", "REPEATED"),
                SchemaField("requires_external", "STRING", "REPEATED"),
                SchemaField("project_urls", "STRING", "REPEATED"),
                SchemaField("created", "TIMESTAMP", "REQUIRED"),
                SchemaField("yanked", "BOOLEAN", "REQUIRED"),
                SchemaField("yanked_reason", "STRING", "NULLABLE"),
                SchemaField("uploader_id", "STRING", "REQUIRED"),
                SchemaField("uploaded_via", "STRING", "NULLABLE"),
                SchemaField(
                    "files",
                    "RECORD",
                    "REPEATED",
                    fields=[
                        SchemaField("filename", "STRING", "REQUIRED"),
                        SchemaField("size", "INTEGER", "REQUIRED"),
                        SchemaField("path", "STRING", "REQUIRED"),
                        SchemaField("python_version", "STRING", "REQUIRED"),
                        SchemaField("packagetype", "STRING", "REQUIRED"),
                        SchemaField("comment_text", "STRING", "NULLABLE"),
                        SchemaField("has_signature", "BOOLEAN", "REQUIRED"),
                        SchemaField("md5_digest", "STRING", "REQUIRED"),
                        SchemaField("sha256_digest", "STRING", "REQUIRED"),
                        SchemaField("blake2_256_digest", "STRING", "REQUIRED"),
                    ],
                ),
            ],
        )
    ]

    @pytest.mark.parametrize(("file", "form", "db_schema"), input_parameters)
    def test_update_row(self, db_request, file, form, db_schema):

        # Process the mocked wtform fields
        for key, value in form.items():
            if isinstance(value, StringField) or isinstance(value, self.ListField):
                value.process(None)

        get_table = pretend.stub(schema=db_schema)
        query = pretend.stub(result=pretend.call_recorder(lambda *a, **kw: ["results"]))
        bigquery = pretend.stub(
            get_table=pretend.call_recorder(lambda t: get_table),
            query=pretend.call_recorder(lambda q: query),
        )

        @pretend.call_recorder
        def find_service(name=None):
            if name == "gcloud.bigquery":
                return bigquery
            raise LookupError

        db_request.find_service = find_service
        db_request.registry.settings = {
            "warehouse.distribution_table": "example.pypi.distributions"
        }

        task = pretend.stub()
        tasks.update_distribution_database(task, db_request, file, form)

        assert bigquery.query.calls == [
            pretend.call(
                (
                    "UPDATE example.pypi.distributions "
                    'SET id="2e1fe167-8078-443e-b21d-07fd1abe5d56",'
                    'metadata_version="1.2",'
                    'project_id="8e8d5a52-bb37-474a-8c2e-d5ec67001405",'
                    'name="OfDABTihRTmE",version="1.0",summary=NULL,'
                    'description_id="7adffac0-eea4-41d2-91e6-15c5fa2d03f7",'
                    'description="an example description",'
                    "description_content_type=NULL,author=NULL,author_email=NULL,"
                    "maintainer=NULL,maintainer_email=NULL,license=NULL,keywords=NULL,"
                    "classifiers=['Environment :: Other Environment'],platform=NULL,"
                    "home_page=NULL,download_url=NULL,requires_python=NULL,"
                    "requires=NULL,provides=NULL,obsoletes=NULL,requires_dist=NULL,"
                    "provides_dist=NULL,obsoletes_dist=NULL,requires_external=NULL,"
                    'project_urls=NULL,created="2020-06-11T00:19:10.875885",'
                    "yanked=False,yanked_reason=NULL,"
                    'uploader_id="3796ac62-3527-4041-be18-f369ae1b24e5",'
                    'uploaded_via="warehouse-tests/6.6.6",'
                    "files=ARRAY_CONCAT(files, [STRUCT("
                    '"OfDABTihRTmE-1.0.tar.gz" AS filename,192 AS size,'
                    '"62/0f/55b4f450c8a20a0a2aea447cc519ac33a7a7043759a8a0'
                    '3685cbac5f4871/OfDABTihRTmE-1.0.tar.gz" AS path,'
                    '"source" AS python_version,"sdist" AS packagetype,'
                    "CAST(NULL AS STRING) AS comment_text,False AS has_signature,"
                    '"7fcdcb15530ea82d2a5daf98a4997c57" AS md5_digest,'
                    '"a983cbea389641f78541e25c14ab1a488ede2641119a5be807e94645c4f3d'
                    '25d" AS sha256_digest,"620f55b4f450c8a20a0a2aea447cc519ac33a7a704'
                    '3759a8a03685cbac5f4871" AS blake2_256_digest)]) '
                    'WHERE id="2e1fe167-8078-443e-b21d-07fd1abe5d56";'
                )
            )
        ]

        assert query.result.calls == [pretend.call()]
        # assert False

    @pytest.mark.parametrize(("file", "form", "db_schema"), input_parameters)
    def test_insert_new_row(self, db_request, file, form, db_schema):

        # Process the mocked wtform fields
        for key, value in form.items():
            if isinstance(value, StringField) or isinstance(value, self.ListField):
                value.process(None)

        @pretend.call_recorder
        def insert_rows(table, json_rows):
            if table != "example.pypi.distributions":
                raise Exception("Incorrect table name")
            return []

        get_table = pretend.stub(schema=db_schema)
        query = pretend.stub(result=pretend.call_recorder(lambda *a, **kw: []))
        bigquery = pretend.stub(
            get_table=pretend.call_recorder(lambda t: get_table),
            query=pretend.call_recorder(lambda q: query),
            insert_rows_json=insert_rows,
        )

        @pretend.call_recorder
        def find_service(name=None):
            if name == "gcloud.bigquery":
                return bigquery
            raise LookupError

        db_request.find_service = find_service
        db_request.registry.settings = {
            "warehouse.distribution_table": "example.pypi.distributions"
        }

        task = pretend.stub()
        tasks.update_distribution_database(task, db_request, file, form)

        assert bigquery.query.calls == [
            pretend.call(
                (
                    "UPDATE example.pypi.distributions "
                    'SET id="2e1fe167-8078-443e-b21d-07fd1abe5d56",'
                    'metadata_version="1.2",'
                    'project_id="8e8d5a52-bb37-474a-8c2e-d5ec67001405",'
                    'name="OfDABTihRTmE",version="1.0",summary=NULL,'
                    'description_id="7adffac0-eea4-41d2-91e6-15c5fa2d03f7",'
                    'description="an example description",'
                    "description_content_type=NULL,author=NULL,author_email=NULL,"
                    "maintainer=NULL,maintainer_email=NULL,license=NULL,keywords=NULL,"
                    "classifiers=['Environment :: Other Environment'],platform=NULL,"
                    "home_page=NULL,download_url=NULL,requires_python=NULL,"
                    "requires=NULL,provides=NULL,obsoletes=NULL,requires_dist=NULL,"
                    "provides_dist=NULL,obsoletes_dist=NULL,requires_external=NULL,"
                    'project_urls=NULL,created="2020-06-11T00:19:10.875885",'
                    "yanked=False,yanked_reason=NULL,"
                    'uploader_id="3796ac62-3527-4041-be18-f369ae1b24e5",'
                    'uploaded_via="warehouse-tests/6.6.6",'
                    "files=ARRAY_CONCAT(files, [STRUCT("
                    '"OfDABTihRTmE-1.0.tar.gz" AS filename,192 AS size,'
                    '"62/0f/55b4f450c8a20a0a2aea447cc519ac33a7a7043759a8a0'
                    '3685cbac5f4871/OfDABTihRTmE-1.0.tar.gz" AS path,'
                    '"source" AS python_version,"sdist" AS packagetype,'
                    "CAST(NULL AS STRING) AS comment_text,False AS has_signature,"
                    '"7fcdcb15530ea82d2a5daf98a4997c57" AS md5_digest,'
                    '"a983cbea389641f78541e25c14ab1a488ede2641119a5be807e94645c4f3d'
                    '25d" AS sha256_digest,"620f55b4f450c8a20a0a2aea447cc519ac33a7a704'
                    '3759a8a03685cbac5f4871" AS blake2_256_digest)]) '
                    'WHERE id="2e1fe167-8078-443e-b21d-07fd1abe5d56";'
                )
            )
        ]
        assert query.result.calls == [pretend.call()]
        assert bigquery.insert_rows_json.calls == [
            pretend.call(
                table="example.pypi.distributions",
                json_rows=[
                    {
                        "id": "2e1fe167-8078-443e-b21d-07fd1abe5d56",
                        "metadata_version": "1.2",
                        "project_id": "8e8d5a52-bb37-474a-8c2e-d5ec67001405",
                        "name": "OfDABTihRTmE",
                        "version": "1.0",
                        "summary": None,
                        "description_id": "7adffac0-eea4-41d2-91e6-15c5fa2d03f7",
                        "description": "an example description",
                        "description_content_type": None,
                        "author": None,
                        "author_email": None,
                        "maintainer": None,
                        "maintainer_email": None,
                        "license": None,
                        "keywords": None,
                        "classifiers": ["Environment :: Other Environment"],
                        "platform": None,
                        "home_page": None,
                        "download_url": None,
                        "requires_python": None,
                        "requires": None,
                        "provides": None,
                        "obsoletes": None,
                        "requires_dist": None,
                        "provides_dist": None,
                        "obsoletes_dist": None,
                        "requires_external": None,
                        "project_urls": None,
                        "created": "2020-06-11T00:19:10.875885",
                        "yanked": False,
                        "yanked_reason": None,
                        "uploader_id": "3796ac62-3527-4041-be18-f369ae1b24e5",
                        "uploaded_via": "warehouse-tests/6.6.6",
                        "files": {
                            "filename": "OfDABTihRTmE-1.0.tar.gz",
                            "size": 192,
                            "path": (
                                "62/0f/55b4f450c8a20a0a2aea447cc519ac33a7a7043"
                                "759a8a03685cbac5f4871/OfDABTihRTmE-1.0.tar.gz"
                            ),
                            "python_version": "source",
                            "packagetype": "sdist",
                            "comment_text": None,
                            "has_signature": False,
                            "md5_digest": "7fcdcb15530ea82d2a5daf98a4997c57",
                            "sha256_digest": (
                                "a983cbea389641f78541e25c14ab1a48"
                                "8ede2641119a5be807e94645c4f3d25d"
                            ),
                            "blake2_256_digest": (
                                "620f55b4f450c8a20a0a2aea447cc51"
                                "9ac33a7a7043759a8a03685cbac5f4871"
                            ),
                        },
                    },
                ],
            )
        ]

    @pytest.mark.parametrize(("file", "form", "db_schema"), input_parameters)
    def test_connection_error(self, db_request, file, form, db_schema):

        # Process the mocked wtform fields
        for key, value in form.items():
            if isinstance(value, StringField) or isinstance(value, self.ListField):
                value.process(None)

        get_table = pretend.stub(schema=db_schema)
        query = pretend.stub(result=pretend.raiser(ConnectionError))
        bigquery = pretend.stub(
            get_table=pretend.call_recorder(lambda t: get_table),
            query=pretend.call_recorder(lambda q: query),
        )

        @pretend.call_recorder
        def find_service(name=None):
            if name == "gcloud.bigquery":
                return bigquery
            raise LookupError

        db_request.find_service = find_service
        db_request.registry.settings = {
            "warehouse.distribution_table": "example.pypi.distributions"
        }

        retry_error = pretend.raiser(MaxRetriesExceededError)
        task = pretend.stub(retry=pretend.call_recorder(retry_error))
        tasks.update_distribution_database(task, db_request, file, form)

        # print(bigquery.query.calls[0])

        assert bigquery.query.calls == [
            pretend.call(
                (
                    "UPDATE example.pypi.distributions "
                    'SET id="2e1fe167-8078-443e-b21d-07fd1abe5d56",'
                    'metadata_version="1.2",'
                    'project_id="8e8d5a52-bb37-474a-8c2e-d5ec67001405",'
                    'name="OfDABTihRTmE",version="1.0",summary=NULL,'
                    'description_id="7adffac0-eea4-41d2-91e6-15c5fa2d03f7",'
                    'description="an example description",'
                    "description_content_type=NULL,author=NULL,author_email=NULL,"
                    "maintainer=NULL,maintainer_email=NULL,license=NULL,keywords=NULL,"
                    "classifiers=['Environment :: Other Environment'],platform=NULL,"
                    "home_page=NULL,download_url=NULL,requires_python=NULL,"
                    "requires=NULL,provides=NULL,obsoletes=NULL,requires_dist=NULL,"
                    "provides_dist=NULL,obsoletes_dist=NULL,requires_external=NULL,"
                    'project_urls=NULL,created="2020-06-11T00:19:10.875885",'
                    "yanked=False,yanked_reason=NULL,"
                    'uploader_id="3796ac62-3527-4041-be18-f369ae1b24e5",'
                    'uploaded_via="warehouse-tests/6.6.6",'
                    "files=ARRAY_CONCAT(files, [STRUCT("
                    '"OfDABTihRTmE-1.0.tar.gz" AS filename,192 AS size,'
                    '"62/0f/55b4f450c8a20a0a2aea447cc519ac33a7a7043759a8a0'
                    '3685cbac5f4871/OfDABTihRTmE-1.0.tar.gz" AS path,'
                    '"source" AS python_version,"sdist" AS packagetype,'
                    "CAST(NULL AS STRING) AS comment_text,False AS has_signature,"
                    '"7fcdcb15530ea82d2a5daf98a4997c57" AS md5_digest,'
                    '"a983cbea389641f78541e25c14ab1a488ede2641119a5be807e94645c4f3d'
                    '25d" AS sha256_digest,"620f55b4f450c8a20a0a2aea447cc519ac33a7a704'
                    '3759a8a03685cbac5f4871" AS blake2_256_digest)]) '
                    'WHERE id="2e1fe167-8078-443e-b21d-07fd1abe5d56";'
                )
            )
        ]
        assert task.retry.calls == [pretend.call(max_retries=5)]


def test_update_description_html(monkeypatch, db_request):
    current_version = "24.0"
    previous_version = "23.0"

    monkeypatch.setattr(readme, "renderer_version", lambda: current_version)

    descriptions = [
        DescriptionFactory.create(html="rendered", rendered_by=current_version),
        DescriptionFactory.create(html="not this one", rendered_by=previous_version),
        DescriptionFactory.create(html="", rendered_by=""),  # Initial migration state
    ]

    tasks.update_description_html(db_request)

    assert set(
        db_request.db.query(
            Description.raw, Description.html, Description.rendered_by
        ).all()
    ) == {
        (descriptions[0].raw, "rendered", current_version),
        (descriptions[1].raw, readme.render(descriptions[1].raw), current_version),
        (descriptions[2].raw, readme.render(descriptions[2].raw), current_version),
    }
