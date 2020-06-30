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

import celery
import elasticsearch
import packaging.version
import pretend
import pytest
import redis

from first import first

import warehouse.search.tasks

from warehouse.search.tasks import (
    SearchLock,
    _project_docs,
    reindex,
    reindex_project,
    unindex_project,
)

from ...common.db.packaging import FileFactory, ProjectFactory, ReleaseFactory


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

    for p in projects:
        for r in releases[p]:
            r.files = [
                FileFactory.create(
                    release=r,
                    filename="{}-{}.tar.gz".format(p.name, r.version),
                    python_version="source",
                )
            ]

    assert list(_project_docs(db_session)) == [
        {
            "_id": p.normalized_name,
            "_type": "doc",
            "_source": {
                "created": p.created,
                "name": p.name,
                "normalized_name": p.normalized_name,
                "version": [r.version for r in prs],
                "latest_version": first(prs, key=lambda r: not r.is_prerelease).version,
                "description": first(
                    prs, key=lambda r: not r.is_prerelease
                ).description.raw,
            },
        }
        for p, prs in sorted(releases.items(), key=lambda x: x[0].id)
    ]


def test_single_project_doc(db_session):
    projects = [ProjectFactory.create() for _ in range(2)]
    releases = {
        p: sorted(
            [ReleaseFactory.create(project=p) for _ in range(3)],
            key=lambda r: packaging.version.parse(r.version),
            reverse=True,
        )
        for p in projects
    }

    for p in projects:
        for r in releases[p]:
            r.files = [
                FileFactory.create(
                    release=r,
                    filename="{}-{}.tar.gz".format(p.name, r.version),
                    python_version="source",
                )
            ]

    assert list(_project_docs(db_session, project_name=projects[1].name)) == [
        {
            "_id": p.normalized_name,
            "_type": "doc",
            "_source": {
                "created": p.created,
                "name": p.name,
                "normalized_name": p.normalized_name,
                "version": [r.version for r in prs],
                "latest_version": first(prs, key=lambda r: not r.is_prerelease).version,
                "description": first(
                    prs, key=lambda r: not r.is_prerelease
                ).description.raw,
            },
        }
        for p, prs in sorted(releases.items(), key=lambda x: x[0].name.lower())
        if p.name == projects[1].name
    ]


def test_project_docs_empty(db_session):
    projects = [ProjectFactory.create() for _ in range(2)]
    releases = {
        p: sorted(
            [ReleaseFactory.create(project=p) for _ in range(3)],
            key=lambda r: packaging.version.parse(r.version),
            reverse=True,
        )
        for p in projects
    }

    project_with_files = projects[0]
    for r in releases[project_with_files]:
        r.files = [
            FileFactory.create(
                release=r,
                filename="{}-{}.tar.gz".format(project_with_files.name, r.version),
                python_version="source",
            )
        ]

    assert list(_project_docs(db_session)) == [
        {
            "_id": p.normalized_name,
            "_type": "doc",
            "_source": {
                "created": p.created,
                "name": p.name,
                "normalized_name": p.normalized_name,
                "version": [r.version for r in prs],
                "latest_version": first(prs, key=lambda r: not r.is_prerelease).version,
                "description": first(
                    prs, key=lambda r: not r.is_prerelease
                ).description.raw,
            },
        }
        for p, prs in sorted(releases.items(), key=lambda x: x[0].id)
        if p == project_with_files
    ]


class FakeESIndices:
    def __init__(self):
        self.indices = {}
        self.aliases = {}

        self.put_settings = pretend.call_recorder(lambda *a, **kw: None)
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


class NotLock:
    def __init__(*a, **kw):
        pass

    def acquire(self):
        return True

    def release(self):
        return True


class TestSearchLock:
    def test_success(self):
        lock_stub = pretend.stub(acquire=pretend.call_recorder(lambda: True))
        r = pretend.stub(lock=lambda *a, **kw: lock_stub)
        test_lock = SearchLock(r)
        test_lock.__enter__()
        assert lock_stub.acquire.calls == [pretend.call()]

    def test_failure(self):
        lock_stub = pretend.stub(acquire=pretend.call_recorder(lambda: False))
        r = pretend.stub(lock=lambda *a, **kw: lock_stub)
        test_lock = SearchLock(r)
        with pytest.raises(redis.exceptions.LockError):
            test_lock.__enter__()
        assert lock_stub.acquire.calls == [pretend.call()]


class TestReindex:
    def test_fails_when_raising(self, db_request, monkeypatch):
        docs = pretend.stub()

        def project_docs(db):
            return docs

        monkeypatch.setattr(warehouse.search.tasks, "_project_docs", project_docs)

        task = pretend.stub()
        es_client = FakeESClient()

        db_request.registry.update({"elasticsearch.index": "warehouse"})
        db_request.registry.settings = {
            "elasticsearch.url": "http://some.url",
            "celery.scheduler_url": "redis://redis:6379/0",
        }
        monkeypatch.setattr(
            warehouse.search.tasks.elasticsearch,
            "Elasticsearch",
            lambda *a, **kw: es_client,
        )

        class TestException(Exception):
            pass

        def parallel_bulk(client, iterable, index=None):
            assert client is es_client
            assert iterable is docs
            assert index == "warehouse-cbcbcbcbcb"
            raise TestException

        monkeypatch.setattr(
            redis.StrictRedis, "from_url", lambda *a, **kw: pretend.stub(lock=NotLock)
        )

        monkeypatch.setattr(warehouse.search.tasks, "parallel_bulk", parallel_bulk)

        monkeypatch.setattr(os, "urandom", lambda n: b"\xcb" * n)

        with pytest.raises(TestException):
            reindex(task, db_request)

        assert es_client.indices.delete.calls == [
            pretend.call(index="warehouse-cbcbcbcbcb")
        ]
        assert es_client.indices.put_settings.calls == []

    def test_retry_on_lock(self, db_request, monkeypatch):
        task = pretend.stub(
            retry=pretend.call_recorder(pretend.raiser(celery.exceptions.Retry))
        )

        db_request.registry.settings = {"celery.scheduler_url": "redis://redis:6379/0"}

        le = redis.exceptions.LockError()
        monkeypatch.setattr(
            redis.StrictRedis,
            "from_url",
            lambda *a, **kw: pretend.stub(lock=pretend.raiser(le)),
        )

        with pytest.raises(celery.exceptions.Retry):
            reindex(task, db_request)

        assert task.retry.calls == [pretend.call(countdown=60, exc=le)]

    def test_successfully_indexes_and_adds_new(self, db_request, monkeypatch):

        docs = pretend.stub()

        def project_docs(db):
            return docs

        monkeypatch.setattr(warehouse.search.tasks, "_project_docs", project_docs)

        task = pretend.stub()
        es_client = FakeESClient()

        db_request.registry.update(
            {"elasticsearch.index": "warehouse", "elasticsearch.shards": 42}
        )
        db_request.registry.settings = {
            "elasticsearch.url": "http://some.url",
            "celery.scheduler_url": "redis://redis:6379/0",
        }
        monkeypatch.setattr(
            warehouse.search.tasks.elasticsearch,
            "Elasticsearch",
            lambda *a, **kw: es_client,
        )
        monkeypatch.setattr(
            redis.StrictRedis, "from_url", lambda *a, **kw: pretend.stub(lock=NotLock)
        )

        parallel_bulk = pretend.call_recorder(lambda client, iterable, index: [None])
        monkeypatch.setattr(warehouse.search.tasks, "parallel_bulk", parallel_bulk)

        monkeypatch.setattr(os, "urandom", lambda n: b"\xcb" * n)

        reindex(task, db_request)

        assert parallel_bulk.calls == [
            pretend.call(es_client, docs, index="warehouse-cbcbcbcbcb")
        ]
        assert es_client.indices.create.calls == [
            pretend.call(
                body={
                    "settings": {
                        "number_of_shards": 42,
                        "number_of_replicas": 0,
                        "refresh_interval": "-1",
                    }
                },
                wait_for_active_shards=42,
                index="warehouse-cbcbcbcbcb",
            )
        ]
        assert es_client.indices.delete.calls == []
        assert es_client.indices.aliases == {"warehouse": ["warehouse-cbcbcbcbcb"]}
        assert es_client.indices.put_settings.calls == [
            pretend.call(
                index="warehouse-cbcbcbcbcb",
                body={"index": {"number_of_replicas": 0, "refresh_interval": "1s"}},
            )
        ]

    def test_successfully_indexes_and_replaces(self, db_request, monkeypatch):
        docs = pretend.stub()
        task = pretend.stub()

        def project_docs(db):
            return docs

        monkeypatch.setattr(warehouse.search.tasks, "_project_docs", project_docs)

        es_client = FakeESClient()
        es_client.indices.indices["warehouse-aaaaaaaaaa"] = None
        es_client.indices.aliases["warehouse"] = ["warehouse-aaaaaaaaaa"]
        db_engine = pretend.stub()

        db_request.registry.update(
            {
                "elasticsearch.index": "warehouse",
                "elasticsearch.shards": 42,
                "sqlalchemy.engine": db_engine,
            }
        )
        db_request.registry.settings = {
            "elasticsearch.url": "http://some.url",
            "celery.scheduler_url": "redis://redis:6379/0",
        }
        monkeypatch.setattr(
            warehouse.search.tasks.elasticsearch,
            "Elasticsearch",
            lambda *a, **kw: es_client,
        )
        monkeypatch.setattr(
            redis.StrictRedis, "from_url", lambda *a, **kw: pretend.stub(lock=NotLock)
        )

        parallel_bulk = pretend.call_recorder(lambda client, iterable, index: [None])
        monkeypatch.setattr(warehouse.search.tasks, "parallel_bulk", parallel_bulk)

        monkeypatch.setattr(os, "urandom", lambda n: b"\xcb" * n)

        reindex(task, db_request)

        assert parallel_bulk.calls == [
            pretend.call(es_client, docs, index="warehouse-cbcbcbcbcb")
        ]
        assert es_client.indices.create.calls == [
            pretend.call(
                body={
                    "settings": {
                        "number_of_shards": 42,
                        "number_of_replicas": 0,
                        "refresh_interval": "-1",
                    }
                },
                wait_for_active_shards=42,
                index="warehouse-cbcbcbcbcb",
            )
        ]
        assert es_client.indices.delete.calls == [pretend.call("warehouse-aaaaaaaaaa")]
        assert es_client.indices.aliases == {"warehouse": ["warehouse-cbcbcbcbcb"]}
        assert es_client.indices.put_settings.calls == [
            pretend.call(
                index="warehouse-cbcbcbcbcb",
                body={"index": {"number_of_replicas": 0, "refresh_interval": "1s"}},
            )
        ]

    def test_client_aws(self, db_request, monkeypatch):
        docs = pretend.stub()

        def project_docs(db):
            return docs

        monkeypatch.setattr(warehouse.search.tasks, "_project_docs", project_docs)

        task = pretend.stub()
        aws4auth_stub = pretend.stub()
        aws4auth = pretend.call_recorder(lambda *a, **kw: aws4auth_stub)
        es_client = FakeESClient()
        es_client_init = pretend.call_recorder(lambda *a, **kw: es_client)

        db_request.registry.update(
            {"elasticsearch.index": "warehouse", "elasticsearch.shards": 42}
        )
        db_request.registry.settings = {
            "aws.key_id": "AAAAAAAAAAAAAAAAAA",
            "aws.secret_key": "deadbeefdeadbeefdeadbeef",
            "elasticsearch.url": "https://some.url?aws_auth=1&region=us-east-2",
            "celery.scheduler_url": "redis://redis:6379/0",
        }
        monkeypatch.setattr(
            warehouse.search.tasks.requests_aws4auth, "AWS4Auth", aws4auth,
        )
        monkeypatch.setattr(
            warehouse.search.tasks.elasticsearch, "Elasticsearch", es_client_init
        )
        monkeypatch.setattr(
            redis.StrictRedis, "from_url", lambda *a, **kw: pretend.stub(lock=NotLock)
        )

        parallel_bulk = pretend.call_recorder(lambda client, iterable, index: [None])
        monkeypatch.setattr(warehouse.search.tasks, "parallel_bulk", parallel_bulk)

        monkeypatch.setattr(os, "urandom", lambda n: b"\xcb" * n)

        reindex(task, db_request)

        assert len(es_client_init.calls) == 1
        assert es_client_init.calls[0].kwargs["hosts"] == ["https://some.url"]
        assert es_client_init.calls[0].kwargs["timeout"] == 30
        assert es_client_init.calls[0].kwargs["retry_on_timeout"] is True
        assert (
            es_client_init.calls[0].kwargs["connection_class"]
            == elasticsearch.connection.http_requests.RequestsHttpConnection
        )
        assert es_client_init.calls[0].kwargs["http_auth"] == aws4auth_stub
        assert aws4auth.calls == [
            pretend.call(
                "AAAAAAAAAAAAAAAAAA", "deadbeefdeadbeefdeadbeef", "us-east-2", "es"
            )
        ]

        assert parallel_bulk.calls == [
            pretend.call(es_client, docs, index="warehouse-cbcbcbcbcb")
        ]
        assert es_client.indices.create.calls == [
            pretend.call(
                body={
                    "settings": {
                        "number_of_shards": 42,
                        "number_of_replicas": 0,
                        "refresh_interval": "-1",
                    }
                },
                wait_for_active_shards=42,
                index="warehouse-cbcbcbcbcb",
            )
        ]
        assert es_client.indices.delete.calls == []
        assert es_client.indices.aliases == {"warehouse": ["warehouse-cbcbcbcbcb"]}
        assert es_client.indices.put_settings.calls == [
            pretend.call(
                index="warehouse-cbcbcbcbcb",
                body={"index": {"number_of_replicas": 0, "refresh_interval": "1s"}},
            )
        ]


class TestPartialReindex:
    def test_reindex_fails_when_raising(self, db_request, monkeypatch):
        docs = pretend.stub()
        task = pretend.stub()

        def project_docs(db, project_name=None):
            return docs

        monkeypatch.setattr(warehouse.search.tasks, "_project_docs", project_docs)

        es_client = FakeESClient()

        db_request.registry.update(
            {"elasticsearch.client": es_client, "elasticsearch.index": "warehouse"}
        )

        class TestException(Exception):
            pass

        def parallel_bulk(client, iterable, index=None):
            assert client is es_client
            assert iterable is docs
            raise TestException

        monkeypatch.setattr(warehouse.search.tasks, "parallel_bulk", parallel_bulk)
        monkeypatch.setattr(
            redis.StrictRedis, "from_url", lambda *a, **kw: pretend.stub(lock=NotLock)
        )

        with pytest.raises(TestException):
            reindex_project(task, db_request, "foo")

        assert es_client.indices.put_settings.calls == []

    def test_unindex_fails_when_raising(self, db_request, monkeypatch):
        task = pretend.stub()

        class TestException(Exception):
            pass

        es_client = FakeESClient()
        es_client.delete = pretend.raiser(TestException)
        monkeypatch.setattr(
            redis.StrictRedis, "from_url", lambda *a, **kw: pretend.stub(lock=NotLock)
        )

        db_request.registry.update(
            {"elasticsearch.client": es_client, "elasticsearch.index": "warehouse"}
        )

        with pytest.raises(TestException):
            unindex_project(task, db_request, "foo")

    def test_unindex_accepts_defeat(self, db_request, monkeypatch):
        task = pretend.stub()

        es_client = FakeESClient()
        es_client.delete = pretend.call_recorder(
            pretend.raiser(elasticsearch.exceptions.NotFoundError)
        )
        monkeypatch.setattr(
            redis.StrictRedis, "from_url", lambda *a, **kw: pretend.stub(lock=NotLock)
        )

        db_request.registry.update(
            {"elasticsearch.client": es_client, "elasticsearch.index": "warehouse"}
        )

        unindex_project(task, db_request, "foo")

        assert es_client.delete.calls == [
            pretend.call(index="warehouse", doc_type="doc", id="foo")
        ]

    def test_unindex_retry_on_lock(self, db_request, monkeypatch):
        task = pretend.stub(
            retry=pretend.call_recorder(pretend.raiser(celery.exceptions.Retry))
        )

        db_request.registry.settings = {"celery.scheduler_url": "redis://redis:6379/0"}

        le = redis.exceptions.LockError()
        monkeypatch.setattr(
            redis.StrictRedis,
            "from_url",
            lambda *a, **kw: pretend.stub(lock=pretend.raiser(le)),
        )

        with pytest.raises(celery.exceptions.Retry):
            unindex_project(task, db_request, "foo")

        assert task.retry.calls == [pretend.call(countdown=60, exc=le)]

    def test_reindex_retry_on_lock(self, db_request, monkeypatch):
        task = pretend.stub(
            retry=pretend.call_recorder(pretend.raiser(celery.exceptions.Retry))
        )

        db_request.registry.settings = {"celery.scheduler_url": "redis://redis:6379/0"}

        le = redis.exceptions.LockError()
        monkeypatch.setattr(
            redis.StrictRedis,
            "from_url",
            lambda *a, **kw: pretend.stub(lock=pretend.raiser(le)),
        )

        with pytest.raises(celery.exceptions.Retry):
            reindex_project(task, db_request, "foo")

        assert task.retry.calls == [pretend.call(countdown=60, exc=le)]

    def test_successfully_indexes(self, db_request, monkeypatch):
        docs = pretend.stub()
        task = pretend.stub()

        def project_docs(db, project_name=None):
            return docs

        monkeypatch.setattr(warehouse.search.tasks, "_project_docs", project_docs)

        es_client = FakeESClient()
        es_client.indices.indices["warehouse-aaaaaaaaaa"] = None
        es_client.indices.aliases["warehouse"] = ["warehouse-aaaaaaaaaa"]
        db_engine = pretend.stub()

        db_request.registry.update(
            {
                "elasticsearch.client": es_client,
                "elasticsearch.index": "warehouse",
                "elasticsearch.shards": 42,
                "sqlalchemy.engine": db_engine,
            }
        )

        parallel_bulk = pretend.call_recorder(
            lambda client, iterable, index=None: [None]
        )
        monkeypatch.setattr(warehouse.search.tasks, "parallel_bulk", parallel_bulk)
        monkeypatch.setattr(
            redis.StrictRedis, "from_url", lambda *a, **kw: pretend.stub(lock=NotLock)
        )

        reindex_project(task, db_request, "foo")

        assert parallel_bulk.calls == [pretend.call(es_client, docs, index="warehouse")]
        assert es_client.indices.create.calls == []
        assert es_client.indices.delete.calls == []
        assert es_client.indices.aliases == {"warehouse": ["warehouse-aaaaaaaaaa"]}
        assert es_client.indices.put_settings.calls == []
