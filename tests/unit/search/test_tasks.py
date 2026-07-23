# SPDX-License-Identifier: Apache-2.0

import os
import types

import celery.exceptions
import opensearchpy
import packaging.version
import pytest
import redis
import redis.lock

from more_itertools import first_true

import warehouse.search.tasks

from warehouse.packaging.models import LifecycleStatus
from warehouse.search.tasks import (
    SearchLock,
    _project_docs,
    reindex,
    reindex_project,
    unindex_project,
)

from ...common.db.packaging import FileFactory, ProjectFactory, ReleaseFactory


def test_project_docs(db_session):
    projects = ProjectFactory.create_batch(2)
    releases = {
        p: sorted(
            ReleaseFactory.create_batch(3, project=p),
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
                    filename=f"{p.name}-{r.version}.tar.gz",
                    python_version="source",
                )
            ]

    # Create an Archived project which should not be included
    archived_project = ProjectFactory.create(
        lifecycle_status=LifecycleStatus.ArchivedNoindex
    )
    archived_releases = ReleaseFactory.create_batch(3, project=archived_project)
    for r in archived_releases:
        r.files = [
            FileFactory.create(
                release=r,
                filename=f"{p.name}-{r.version}.tar.gz",
                python_version="source",
            )
        ]

    assert list(_project_docs(db_session)) == [
        {
            "_id": p.normalized_name,
            "_source": {
                "created": p.created,
                "name": p.name,
                "normalized_name": p.normalized_name,
                "description": first_true(
                    prs, pred=lambda r: not r.is_prerelease
                ).description.raw,
            },
        }
        for p, prs in sorted(releases.items(), key=lambda x: x[0].normalized_name)
    ]


def test_single_project_doc(db_session):
    projects = ProjectFactory.create_batch(2)
    releases = {
        p: sorted(
            ReleaseFactory.create_batch(3, project=p),
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
                    filename=f"{p.name}-{r.version}.tar.gz",
                    python_version="source",
                )
            ]

    assert list(_project_docs(db_session, project_name=projects[1].name)) == [
        {
            "_id": p.normalized_name,
            "_source": {
                "created": p.created,
                "name": p.name,
                "normalized_name": p.normalized_name,
                "description": first_true(
                    prs, pred=lambda r: not r.is_prerelease
                ).description.raw,
            },
        }
        for p, prs in sorted(releases.items(), key=lambda x: x[0].name.lower())
        if p.name == projects[1].name
    ]


def test_project_docs_empty(db_session):
    projects = ProjectFactory.create_batch(2)
    releases = {
        p: sorted(
            ReleaseFactory.create_batch(3, project=p),
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
                filename=f"{project_with_files.name}-{r.version}.tar.gz",
                python_version="source",
            )
        ]

    assert list(_project_docs(db_session)) == [
        {
            "_id": p.normalized_name,
            "_source": {
                "created": p.created,
                "name": p.name,
                "normalized_name": p.normalized_name,
                "description": first_true(
                    prs, pred=lambda r: not r.is_prerelease
                ).description.raw,
            },
        }
        for p, prs in sorted(releases.items(), key=lambda x: x[0].id)
        if p == project_with_files
    ]


class FakeESIndices:
    def __init__(self, mocker):
        self.indices = {}
        self.aliases = {}

        self.put_settings = mocker.stub(name="put_settings")
        self.delete = mocker.stub(name="delete")
        self.create = mocker.stub(name="create")

    def exists_alias(self, name):
        return name in self.aliases

    def get_alias(self, name):
        return self.aliases[name]

    def put_alias(self, name, index):
        self.aliases.setdefault(name, []).append(index)

    def remove_alias(self, name, alias):
        self.aliases[name] = [n for n in self.aliases[name] if n != alias]

    def update_aliases(self, *, body):
        for items in body["actions"]:
            for action, values in items.items():
                if action == "add":
                    self.put_alias(values["alias"], values["index"])
                elif action == "remove":
                    self.remove_alias(values["alias"], values["index"])
                else:
                    pytest.fail(f"Unknown action: {action!r}.")


class FakeESClient:
    def __init__(self, mocker):
        self.indices = FakeESIndices(mocker)


class NotLock:
    def __init__(*a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass


class TestSearchLock:
    def test_is_subclass_of_redis_lock(self, mockredis):
        search_lock = SearchLock(redis_client=mockredis)

        assert isinstance(search_lock, redis.lock.Lock)
        assert search_lock.name == "search-index"


class TestReindex:
    def test_fails_when_raising(self, db_request, mocker):
        docs = mocker.sentinel.docs
        mocker.patch.object(warehouse.search.tasks, "_project_docs", return_value=docs)

        es_client = FakeESClient(mocker)

        db_request.registry.update({"opensearch.index": "warehouse"})
        db_request.registry.settings = {
            "opensearch.url": "http://some.url",
            "celery.scheduler_url": "redis://redis:6379/0",
        }
        mocker.patch.object(
            warehouse.search.tasks.opensearchpy, "OpenSearch", return_value=es_client
        )

        class TestError(Exception):
            pass

        def parallel_bulk(
            client, iterable, index=None, chunk_size=None, max_chunk_bytes=None
        ):
            assert client is es_client
            assert iterable is docs
            assert index == "warehouse-cbcbcbcbcb"
            raise TestError

        mocker.patch.object(warehouse.search.tasks, "SearchLock", NotLock)
        mocker.patch.object(
            warehouse.search.tasks, "parallel_bulk", side_effect=parallel_bulk
        )
        mocker.patch.object(os, "urandom", side_effect=lambda n: b"\xcb" * n)

        with pytest.raises(TestError):
            reindex(mocker.sentinel.task, db_request)

        es_client.indices.delete.assert_called_once_with(index="warehouse-cbcbcbcbcb")
        es_client.indices.put_settings.assert_not_called()

    def test_retry_on_lock(self, db_request, mocker):
        task = types.SimpleNamespace(
            retry=mocker.Mock(side_effect=celery.exceptions.Retry)
        )

        db_request.registry.settings = {"celery.scheduler_url": "redis://redis:6379/0"}

        le = redis.exceptions.LockError("Failed to acquire lock")
        mocker.patch.object(SearchLock, "acquire", side_effect=le)

        with pytest.raises(celery.exceptions.Retry):
            reindex(task, db_request)

        task.retry.assert_called_once_with(countdown=60, exc=le)

    def test_successfully_indexes_and_adds_new(self, db_request, mocker):
        docs = mocker.sentinel.docs
        mocker.patch.object(warehouse.search.tasks, "_project_docs", return_value=docs)

        es_client = FakeESClient(mocker)

        db_request.registry.update(
            {"opensearch.index": "warehouse", "opensearch.shards": 42}
        )
        db_request.registry.settings = {
            "opensearch.url": "http://some.url",
            "celery.scheduler_url": "redis://redis:6379/0",
        }
        mocker.patch.object(
            warehouse.search.tasks.opensearchpy, "OpenSearch", return_value=es_client
        )
        mocker.patch.object(warehouse.search.tasks, "SearchLock", NotLock)

        parallel_bulk = mocker.patch.object(
            warehouse.search.tasks, "parallel_bulk", return_value=[None]
        )
        mocker.patch.object(os, "urandom", side_effect=lambda n: b"\xcb" * n)

        reindex(mocker.sentinel.task, db_request)

        parallel_bulk.assert_called_once_with(
            es_client,
            docs,
            index="warehouse-cbcbcbcbcb",
            chunk_size=100,
            max_chunk_bytes=10485760,
        )
        es_client.indices.create.assert_called_once_with(
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
        es_client.indices.delete.assert_not_called()
        assert es_client.indices.aliases == {"warehouse": ["warehouse-cbcbcbcbcb"]}
        es_client.indices.put_settings.assert_called_once_with(
            index="warehouse-cbcbcbcbcb",
            body={"index": {"number_of_replicas": 0, "refresh_interval": "1s"}},
        )

    def test_successfully_indexes_and_replaces(self, db_request, mocker):
        docs = mocker.sentinel.docs
        mocker.patch.object(warehouse.search.tasks, "_project_docs", return_value=docs)

        es_client = FakeESClient(mocker)
        es_client.indices.indices["warehouse-aaaaaaaaaa"] = None
        es_client.indices.aliases["warehouse"] = ["warehouse-aaaaaaaaaa"]

        db_request.registry.update(
            {
                "opensearch.index": "warehouse",
                "opensearch.shards": 42,
                "sqlalchemy.engine": mocker.sentinel.db_engine,
            }
        )
        db_request.registry.settings = {
            "opensearch.url": "http://some.url",
            "celery.scheduler_url": "redis://redis:6379/0",
        }
        mocker.patch.object(
            warehouse.search.tasks.opensearchpy, "OpenSearch", return_value=es_client
        )
        mocker.patch.object(warehouse.search.tasks, "SearchLock", NotLock)

        parallel_bulk = mocker.patch.object(
            warehouse.search.tasks, "parallel_bulk", return_value=[None]
        )
        mocker.patch.object(os, "urandom", side_effect=lambda n: b"\xcb" * n)

        reindex(mocker.sentinel.task, db_request)

        parallel_bulk.assert_called_once_with(
            es_client,
            docs,
            index="warehouse-cbcbcbcbcb",
            chunk_size=100,
            max_chunk_bytes=10485760,
        )
        es_client.indices.create.assert_called_once_with(
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
        es_client.indices.delete.assert_called_once_with(index="warehouse-aaaaaaaaaa")
        assert es_client.indices.aliases == {"warehouse": ["warehouse-cbcbcbcbcb"]}
        es_client.indices.put_settings.assert_called_once_with(
            index="warehouse-cbcbcbcbcb",
            body={"index": {"number_of_replicas": 0, "refresh_interval": "1s"}},
        )

    def test_client_aws(self, db_request, mocker):
        docs = mocker.sentinel.docs
        mocker.patch.object(warehouse.search.tasks, "_project_docs", return_value=docs)

        signer_auth = mocker.patch.object(
            warehouse.search.tasks,
            "RequestsAWSV4SignerAuth",
            return_value=mocker.sentinel.signer_auth,
        )
        credentials = mocker.patch.object(
            warehouse.search.tasks,
            "Credentials",
            return_value=mocker.sentinel.credentials,
        )
        es_client = FakeESClient(mocker)
        es_client_init = mocker.patch.object(
            warehouse.search.tasks.opensearchpy, "OpenSearch", return_value=es_client
        )

        db_request.registry.update(
            {"opensearch.index": "warehouse", "opensearch.shards": 42}
        )
        db_request.registry.settings = {
            "aws.key_id": "AAAAAAAAAAAAAAAAAA",
            "aws.secret_key": "deadbeefdeadbeefdeadbeef",
            "opensearch.url": "https://some.url?aws_auth=1&region=us-east-2",
            "celery.scheduler_url": "redis://redis:6379/0",
        }
        mocker.patch.object(warehouse.search.tasks, "SearchLock", NotLock)

        parallel_bulk = mocker.patch.object(
            warehouse.search.tasks, "parallel_bulk", return_value=[None]
        )
        mocker.patch.object(os, "urandom", side_effect=lambda n: b"\xcb" * n)

        reindex(mocker.sentinel.task, db_request)

        assert es_client_init.call_count == 1
        kwargs = es_client_init.call_args.kwargs
        assert kwargs["hosts"] == ["https://some.url"]
        assert kwargs["timeout"] == 30
        assert kwargs["retry_on_timeout"] is True
        assert (
            kwargs["connection_class"]
            == opensearchpy.connection.http_requests.RequestsHttpConnection
        )
        assert kwargs["http_auth"] == mocker.sentinel.signer_auth
        credentials.assert_called_once_with(
            access_key="AAAAAAAAAAAAAAAAAA",
            secret_key="deadbeefdeadbeefdeadbeef",
        )
        signer_auth.assert_called_once_with(
            mocker.sentinel.credentials, "us-east-2", "es"
        )

        parallel_bulk.assert_called_once_with(
            es_client,
            docs,
            index="warehouse-cbcbcbcbcb",
            chunk_size=100,
            max_chunk_bytes=10485760,
        )
        es_client.indices.create.assert_called_once_with(
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
        es_client.indices.delete.assert_not_called()
        assert es_client.indices.aliases == {"warehouse": ["warehouse-cbcbcbcbcb"]}
        es_client.indices.put_settings.assert_called_once_with(
            index="warehouse-cbcbcbcbcb",
            body={"index": {"number_of_replicas": 0, "refresh_interval": "1s"}},
        )


class TestPartialReindex:
    def test_reindex_fails_when_raising(self, db_request, mocker):
        docs = mocker.sentinel.docs

        db_request.registry.settings = {"celery.scheduler_url": "redis://redis:6379/0"}

        mocker.patch.object(warehouse.search.tasks, "_project_docs", return_value=docs)

        es_client = FakeESClient(mocker)

        db_request.registry.update(
            {"opensearch.client": es_client, "opensearch.index": "warehouse"}
        )

        class TestError(Exception):
            pass

        def parallel_bulk(client, iterable, index=None):
            assert client is es_client
            assert iterable is docs
            raise TestError

        mocker.patch.object(
            warehouse.search.tasks, "parallel_bulk", side_effect=parallel_bulk
        )
        mocker.patch.object(warehouse.search.tasks, "SearchLock", NotLock)

        with pytest.raises(TestError):
            reindex_project(mocker.sentinel.task, db_request, "foo")

        es_client.indices.put_settings.assert_not_called()

    def test_unindex_fails_when_raising(self, db_request, mocker):
        db_request.registry.settings = {"celery.scheduler_url": "redis://redis:6379/0"}

        class TestError(Exception):
            pass

        es_client = FakeESClient(mocker)
        es_client.delete = mocker.Mock(side_effect=TestError)
        mocker.patch.object(warehouse.search.tasks, "SearchLock", NotLock)

        db_request.registry.update(
            {"opensearch.client": es_client, "opensearch.index": "warehouse"}
        )

        with pytest.raises(TestError):
            unindex_project(mocker.sentinel.task, db_request, "foo")

    def test_unindex_accepts_defeat(self, db_request, mocker):
        db_request.registry.settings = {"celery.scheduler_url": "redis://redis:6379/0"}

        es_client = FakeESClient(mocker)
        es_client.delete = mocker.Mock(
            side_effect=opensearchpy.exceptions.NotFoundError
        )
        mocker.patch.object(warehouse.search.tasks, "SearchLock", NotLock)

        db_request.registry.update(
            {"opensearch.client": es_client, "opensearch.index": "warehouse"}
        )

        unindex_project(mocker.sentinel.task, db_request, "foo")

        es_client.delete.assert_called_once_with(index="warehouse", id="foo")

    def test_unindex_retry_on_lock(self, db_request, mocker):
        task = types.SimpleNamespace(
            retry=mocker.Mock(side_effect=celery.exceptions.Retry)
        )

        db_request.registry.settings = {"celery.scheduler_url": "redis://redis:6379/0"}

        le = redis.exceptions.LockError("Failed to acquire lock")
        mocker.patch.object(SearchLock, "acquire", side_effect=le)

        with pytest.raises(celery.exceptions.Retry):
            unindex_project(task, db_request, "foo")

        task.retry.assert_called_once_with(countdown=60, exc=le)

    def test_reindex_retry_on_lock(self, db_request, mocker):
        task = types.SimpleNamespace(
            retry=mocker.Mock(side_effect=celery.exceptions.Retry)
        )

        db_request.registry.settings = {"celery.scheduler_url": "redis://redis:6379/0"}

        le = redis.exceptions.LockError("Failed to acquire lock")
        mocker.patch.object(SearchLock, "acquire", side_effect=le)

        with pytest.raises(celery.exceptions.Retry):
            reindex_project(task, db_request, "foo")

        task.retry.assert_called_once_with(countdown=60, exc=le)

    def test_successfully_indexes(self, db_request, mocker):
        docs = mocker.sentinel.docs

        db_request.registry.settings = {"celery.scheduler_url": "redis://redis:6379/0"}

        mocker.patch.object(warehouse.search.tasks, "_project_docs", return_value=docs)

        es_client = FakeESClient(mocker)
        es_client.indices.indices["warehouse-aaaaaaaaaa"] = None
        es_client.indices.aliases["warehouse"] = ["warehouse-aaaaaaaaaa"]

        db_request.registry.update(
            {
                "opensearch.client": es_client,
                "opensearch.index": "warehouse",
                "opensearch.shards": 42,
                "sqlalchemy.engine": mocker.sentinel.db_engine,
            }
        )

        parallel_bulk = mocker.patch.object(
            warehouse.search.tasks, "parallel_bulk", return_value=[None]
        )
        mocker.patch.object(warehouse.search.tasks, "SearchLock", NotLock)

        reindex_project(mocker.sentinel.task, db_request, "foo")

        parallel_bulk.assert_called_once_with(es_client, docs, index="warehouse")
        es_client.indices.create.assert_not_called()
        es_client.indices.delete.assert_not_called()
        assert es_client.indices.aliases == {"warehouse": ["warehouse-aaaaaaaaaa"]}
        es_client.indices.put_settings.assert_not_called()
