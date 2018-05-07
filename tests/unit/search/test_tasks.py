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

import os

import packaging.version
import pretend
import pytest

from first import first

import warehouse.search.tasks
from warehouse.search.tasks import reindex, _project_docs

from ...common.db.packaging import ProjectFactory, ReleaseFactory


def test_project_docs(db_session):
    projects = [ProjectFactory.create() for _ in range(2)]
    releases = {
        p: sorted(
            [ReleaseFactory.create(project=p) for _ in range(3)],
            key=lambda r: packaging.version.parse(r.version),
            reverse=True,
        )
        for p in projects
    }

    assert list(_project_docs(db_session)) == [
        {
            "_id": p.normalized_name,
            "_type": "project",
            "_source": {
                "created": p.created,
                "name": p.name,
                "normalized_name": p.normalized_name,
                "version": [r.version for r in prs],
                "latest_version": first(
                    prs,
                    key=lambda r: not r.is_prerelease,
                ).version,
            },
        }
        for p, prs in sorted(releases.items(), key=lambda x: x[0].name.lower())
    ]


class FakeESIndices:

    def __init__(self):
        self.indices = {}
        self.aliases = {}

        self.put_settings = pretend.call_recorder(lambda *a, **kw: None)
        self.forcemerge = pretend.call_recorder(lambda *a, **kw: None)
        self.delete = pretend.call_recorder(lambda *a, **kw: None)
        self.create = pretend.call_recorder(lambda *a, **kw: None)

    def exists_alias(self, name):
        return name in self.aliases

    def get_alias(self, name):
        return self.aliases[name]

    def put_alias(self, name, index):
        self.aliases.setdefault(name, []).append(index)

    def remove_alias(self, name, alias):
        self.aliases[name] = [n for n in self.aliases[name] if n != alias]
        if not self.aliases[name]:
            del self.aliases[name]

    def update_aliases(self, body):
        for items in body["actions"]:
            for action, values in items.items():
                if action == "add":
                    self.put_alias(values["alias"], values["index"])
                elif action == "remove":
                    self.remove_alias(values["alias"], values["index"])
                else:
                    raise ValueError("Unknown action: {!r}.".format(action))


class FakeESClient:

    def __init__(self):
        self.indices = FakeESIndices()


class TestReindex:

    def test_fails_when_raising(self, db_request, monkeypatch):
        docs = pretend.stub()

        def project_docs(db):
            return docs

        monkeypatch.setattr(
            warehouse.search.tasks,
            "_project_docs",
            project_docs,
        )

        es_client = FakeESClient()

        db_request.registry.update(
            {
                "elasticsearch.index": "warehouse",
            },
        )
        db_request.registry.settings = {
            "elasticsearch.url": "http://some.url",
        }
        monkeypatch.setattr(
            warehouse.search.tasks.elasticsearch,
            "Elasticsearch",
            lambda *a, **kw: es_client
        )

        class TestException(Exception):
            pass

        def parallel_bulk(client, iterable):
            assert client is es_client
            assert iterable is docs
            raise TestException

        monkeypatch.setattr(
            warehouse.search.tasks, "parallel_bulk", parallel_bulk)

        monkeypatch.setattr(os, "urandom", lambda n: b"\xcb" * n)

        with pytest.raises(TestException):
            reindex(db_request)

        assert es_client.indices.delete.calls == [
            pretend.call(index='warehouse-cbcbcbcbcb'),
        ]
        assert es_client.indices.put_settings.calls == []
        assert es_client.indices.forcemerge.calls == []

    def test_successfully_indexes_and_adds_new(self, db_request, monkeypatch):

        docs = pretend.stub()

        def project_docs(db):
            return docs

        monkeypatch.setattr(
            warehouse.search.tasks,
            "_project_docs",
            project_docs,
        )

        es_client = FakeESClient()

        db_request.registry.update(
            {
                "elasticsearch.index": "warehouse",
                "elasticsearch.shards": 42,
            }
        )
        db_request.registry.settings = {
            "elasticsearch.url": "http://some.url",
        }
        monkeypatch.setattr(
            warehouse.search.tasks.elasticsearch,
            "Elasticsearch",
            lambda *a, **kw: es_client
        )

        parallel_bulk = pretend.call_recorder(lambda client, iterable: [None])
        monkeypatch.setattr(
            warehouse.search.tasks, "parallel_bulk", parallel_bulk)

        monkeypatch.setattr(os, "urandom", lambda n: b"\xcb" * n)

        reindex(db_request)

        assert parallel_bulk.calls == [pretend.call(es_client, docs)]
        assert es_client.indices.create.calls == [
            pretend.call(
                body={
                    'settings': {
                        'number_of_shards': 42,
                        'number_of_replicas': 0,
                        'refresh_interval': '-1',
                    }
                },
                wait_for_active_shards=42,
                index='warehouse-cbcbcbcbcb',
            )
        ]
        assert es_client.indices.delete.calls == []
        assert es_client.indices.aliases == {
            "warehouse": ["warehouse-cbcbcbcbcb"],
        }
        assert es_client.indices.put_settings.calls == [
            pretend.call(
                index='warehouse-cbcbcbcbcb',
                body={
                    'index': {
                        'number_of_replicas': 0,
                        'refresh_interval': '1s',
                    },
                },
            )
        ]
        assert es_client.indices.forcemerge.calls == [
            pretend.call(index='warehouse-cbcbcbcbcb')
        ]

    def test_successfully_indexes_and_replaces(self, db_request, monkeypatch):
        docs = pretend.stub()

        def project_docs(db):
            return docs

        monkeypatch.setattr(
            warehouse.search.tasks,
            "_project_docs",
            project_docs,
        )

        es_client = FakeESClient()
        es_client.indices.indices["warehouse-aaaaaaaaaa"] = None
        es_client.indices.aliases["warehouse"] = ["warehouse-aaaaaaaaaa"]
        db_engine = pretend.stub()

        db_request.registry.update(
            {
                "elasticsearch.index": "warehouse",
                "elasticsearch.shards": 42,
                "sqlalchemy.engine": db_engine,
            },
        )
        db_request.registry.settings = {
            "elasticsearch.url": "http://some.url",
        }
        monkeypatch.setattr(
            warehouse.search.tasks.elasticsearch,
            "Elasticsearch",
            lambda *a, **kw: es_client
        )

        parallel_bulk = pretend.call_recorder(lambda client, iterable: [None])
        monkeypatch.setattr(
            warehouse.search.tasks, "parallel_bulk", parallel_bulk)

        monkeypatch.setattr(os, "urandom", lambda n: b"\xcb" * n)

        reindex(db_request)

        assert parallel_bulk.calls == [pretend.call(es_client, docs)]
        assert es_client.indices.create.calls == [
            pretend.call(
                body={
                    'settings': {
                        'number_of_shards': 42,
                        'number_of_replicas': 0,
                        'refresh_interval': '-1',
                    }
                },
                wait_for_active_shards=42,
                index='warehouse-cbcbcbcbcb',
            )
        ]
        assert es_client.indices.delete.calls == [
            pretend.call('warehouse-aaaaaaaaaa'),
        ]
        assert es_client.indices.aliases == {
            "warehouse": ["warehouse-cbcbcbcbcb"],
        }
        assert es_client.indices.put_settings.calls == [
            pretend.call(
                index='warehouse-cbcbcbcbcb',
                body={
                    'index': {
                        'number_of_replicas': 0,
                        'refresh_interval': '1s',
                    },
                },
            )
        ]
        assert es_client.indices.forcemerge.calls == [
            pretend.call(index='warehouse-cbcbcbcbcb')
        ]
