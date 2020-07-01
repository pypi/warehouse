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

from google.cloud.bigquery import Row, SchemaField
from wtforms import Field, Form, StringField

from warehouse.cache.origin import IOriginCache
from warehouse.packaging.models import Description, Project
from warehouse.packaging.tasks import (
    compute_trending,
    sync_bigquery_release_files,
    update_bigquery_release_files,
    update_description_html,
)
from warehouse.utils import readme

from ...common.db.classifiers import ClassifierFactory
from ...common.db.packaging import (
    DependencyFactory,
    DescriptionFactory,
    FileFactory,
    ProjectFactory,
    ReleaseFactory,
)


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

        compute_trending(db_request)

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


bq_schema = [
    SchemaField("metadata_version", "STRING", "NULLABLE"),
    SchemaField("name", "STRING", "REQUIRED"),
    SchemaField("version", "STRING", "REQUIRED"),
    SchemaField("summary", "STRING", "NULLABLE"),
    SchemaField("description", "STRING", "NULLABLE"),
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
    SchemaField("uploaded_via", "STRING", "NULLABLE"),
    SchemaField("upload_time", "TIMESTAMP", "REQUIRED"),
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
]


class TestUpdateBigQueryMetadata:
    class ListField(Field):
        def process_formdata(self, valuelist):
            self.data = [v.strip() for v in valuelist if v.strip()]

    input_parameters = [
        (
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
            bq_schema,
        )
    ]

    @pytest.mark.parametrize(("form_factory", "bq_schema"), input_parameters)
    def test_insert_new_row(self, db_request, form_factory, bq_schema):
        project = ProjectFactory.create()
        release = ReleaseFactory.create(project=project, version="1.0")
        release_file = FileFactory.create(
            release=release, filename=f"foobar-{release.version}.tar.gz"
        )

        # Process the mocked wtform fields
        for key, value in form_factory.items():
            if isinstance(value, StringField) or isinstance(value, self.ListField):
                value.process(None)

        @pretend.call_recorder
        def insert_rows(table, json_rows):
            if table != "example.pypi.distributions":
                raise Exception("Incorrect table name")
            return []

        get_table = pretend.stub(schema=bq_schema)
        bigquery = pretend.stub(
            get_table=pretend.call_recorder(lambda t: get_table),
            insert_rows_json=insert_rows,
        )

        @pretend.call_recorder
        def find_service(name=None):
            if name == "gcloud.bigquery":
                return bigquery
            raise LookupError

        db_request.find_service = find_service
        db_request.registry.settings = {
            "warehouse.release_files_table": "example.pypi.distributions"
        }

        task = pretend.stub()
        update_bigquery_release_files(task, db_request, release_file, form_factory)

        assert db_request.find_service.calls == [pretend.call(name="gcloud.bigquery")]
        assert bigquery.get_table.calls == [pretend.call("example.pypi.distributions")]
        assert bigquery.insert_rows_json.calls == [
            pretend.call(
                table="example.pypi.distributions",
                json_rows=[
                    {
                        "metadata_version": form_factory["metadata_version"].data,
                        "name": form_factory["name"].data,
                        "version": release_file.release.version,
                        "summary": form_factory["summary"].data or None,
                        "description": form_factory["description"].data or None,
                        "description_content_type": form_factory[
                            "description_content_type"
                        ].data
                        or None,
                        "author": form_factory["author"].data or None,
                        "author_email": form_factory["author_email"].data or None,
                        "maintainer": form_factory["maintainer"].data or None,
                        "maintainer_email": form_factory["maintainer_email"].data
                        or None,
                        "license": form_factory["license"].data or None,
                        "keywords": form_factory["description_content_type"].data
                        or None,
                        "classifiers": form_factory["classifiers"].data or [],
                        "platform": form_factory["platform"].data or [],
                        "home_page": form_factory["home_page"].data or None,
                        "download_url": form_factory["download_url"].data or None,
                        "requires_python": form_factory["requires_python"].data or None,
                        "requires": form_factory["requires"].data or [],
                        "provides": form_factory["provides"].data or [],
                        "obsoletes": form_factory["obsoletes"].data or [],
                        "requires_dist": form_factory["requires_dist"].data or [],
                        "provides_dist": form_factory["provides_dist"].data or [],
                        "obsoletes_dist": form_factory["obsoletes_dist"].data or [],
                        "requires_external": form_factory["requires_external"].data
                        or [],
                        "project_urls": form_factory["project_urls"].data or [],
                        "uploaded_via": release_file.uploaded_via,
                        "upload_time": release_file.upload_time.isoformat(),
                        "filename": release_file.filename,
                        "size": release_file.size,
                        "path": release_file.path,
                        "python_version": release_file.python_version,
                        "packagetype": release_file.packagetype,
                        "comment_text": release_file.comment_text or None,
                        "has_signature": release_file.has_signature,
                        "md5_digest": release_file.md5_digest,
                        "sha256_digest": release_file.sha256_digest,
                        "blake2_256_digest": release_file.blake2_256_digest,
                    },
                ],
            )
        ]


class TestSyncBigQueryMetadata:
    @pytest.mark.parametrize("bq_schema", [bq_schema])
    def test_sync_rows(self, db_request, bq_schema):
        project = ProjectFactory.create()
        description = DescriptionFactory.create()
        release = ReleaseFactory.create(project=project, description=description)
        release_file = FileFactory.create(
            release=release, filename=f"foobar-{release.version}.tar.gz"
        )
        release_file2 = FileFactory.create(
            release=release, filename=f"fizzbuzz-{release.version}.tar.gz"
        )
        release._classifiers.append(ClassifierFactory.create(classifier="foo :: bar"))
        release._classifiers.append(ClassifierFactory.create(classifier="foo :: baz"))
        release._classifiers.append(ClassifierFactory.create(classifier="fiz :: buz"))
        DependencyFactory.create(release=release, kind=1)
        DependencyFactory.create(release=release, kind=1)
        DependencyFactory.create(release=release, kind=2)
        DependencyFactory.create(release=release, kind=3)
        DependencyFactory.create(release=release, kind=4)

        query = pretend.stub(
            result=pretend.call_recorder(
                lambda *a, **kw: [{"md5_digest": release_file2.md5_digest}]
            )
        )
        get_table = pretend.stub(schema=bq_schema)
        bigquery = pretend.stub(
            get_table=pretend.call_recorder(lambda t: get_table),
            insert_rows_json=pretend.call_recorder(lambda *a, **kw: []),
            query=pretend.call_recorder(lambda q: query),
        )

        @pretend.call_recorder
        def find_service(name=None):
            if name == "gcloud.bigquery":
                return bigquery
            raise LookupError

        db_request.find_service = find_service
        db_request.registry.settings = {
            "warehouse.release_files_table": "example.pypi.distributions"
        }

        sync_bigquery_release_files(db_request)

        assert db_request.find_service.calls == [pretend.call(name="gcloud.bigquery")]
        assert bigquery.get_table.calls == [pretend.call("example.pypi.distributions")]
        assert bigquery.query.calls == [
            pretend.call("SELECT md5_digest FROM example.pypi.distributions")
        ]
        assert bigquery.insert_rows_json.calls == [
            pretend.call(
                table="example.pypi.distributions",
                json_rows=[
                    {
                        "metadata_version": None,
                        "name": project.name,
                        "version": release.version,
                        "summary": release.summary,
                        "description": description.raw,
                        "description_content_type": description.content_type or None,
                        "author": release.author or None,
                        "author_email": release.author_email or None,
                        "maintainer": release.maintainer or None,
                        "maintainer_email": release.maintainer_email or None,
                        "license": release.license or None,
                        "keywords": release.keywords or None,
                        "classifiers": release.classifiers or [],
                        "platform": release.platform or [],
                        "home_page": release.home_page or None,
                        "download_url": release.download_url or None,
                        "requires_python": release.requires_python or None,
                        "requires": release.requires or [],
                        "provides": release.provides or [],
                        "obsoletes": release.obsoletes or [],
                        "requires_dist": release.requires_dist or [],
                        "provides_dist": release.provides_dist or [],
                        "obsoletes_dist": release.obsoletes_dist or [],
                        "requires_external": release.requires_external or [],
                        "project_urls": release.project_urls or [],
                        "uploaded_via": release_file.uploaded_via,
                        "upload_time": release_file.upload_time.isoformat(),
                        "filename": release_file.filename,
                        "size": release_file.size,
                        "path": release_file.path,
                        "python_version": release_file.python_version,
                        "packagetype": release_file.packagetype,
                        "comment_text": release_file.comment_text or None,
                        "has_signature": release_file.has_signature,
                        "md5_digest": release_file.md5_digest,
                        "sha256_digest": release_file.sha256_digest,
                        "blake2_256_digest": release_file.blake2_256_digest,
                    },
                ],
            )
        ]
