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

import warehouse.cli.search.reindex

from warehouse.cli.search.reindex import reindex, _project_docs

from ....common.db.packaging import ProjectFactory, ReleaseFactory


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
                "name": p.name,
                "normalized_name": p.normalized_name,
                "version": [r.version for r in prs],
                "uploader_name": prs[0].uploader.name,
                "uploader_username": prs[0].uploader.username,
            },
        }
        for p, prs in sorted(releases.items(), key=lambda x: x[0].name.lower())
    ]


class FakeESIndices:

    def __init__(self):
        self.indices = {}
        self.aliases = {}

    def create(self, index, body):
        self.indices[index] = body

    def delete(self, index):
        self.indices.pop(index, None)

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

    def test_fails_when_raising(self, monkeypatch, cli):
        sess_obj = pretend.stub(
            execute=pretend.call_recorder(lambda q: None),
            rollback=pretend.call_recorder(lambda: None),
            close=pretend.call_recorder(lambda: None),
        )
        sess_cls = pretend.call_recorder(lambda bind: sess_obj)
        monkeypatch.setattr(warehouse.cli.search.reindex, "Session", sess_cls)

        docs = pretend.stub()

        def project_docs(db):
            return docs

        monkeypatch.setattr(
            warehouse.cli.search.reindex,
            "_project_docs",
            project_docs,
        )

        es_client = FakeESClient()
        db_engine = pretend.stub()

        config = pretend.stub(
            registry={
                "elasticsearch.client": es_client,
                "elasticsearch.index": "warehouse",
                "sqlalchemy.engine": db_engine,
            },
        )

        class TestException(Exception):
            pass

        def bulk(client, iterable):
            assert client is es_client
            assert iterable is docs
            raise TestException
        monkeypatch.setattr(warehouse.cli.search.reindex, "bulk", bulk)

        result = cli.invoke(reindex, obj=config)

        assert result.exit_code == -1
        assert isinstance(result.exception, TestException)
        assert sess_cls.calls == [pretend.call(bind=db_engine)]
        assert sess_obj.execute.calls == [
            pretend.call(
                """ BEGIN TRANSACTION
                ISOLATION LEVEL SERIALIZABLE
                READ ONLY
                DEFERRABLE
            """
            ),
            pretend.call("SET statement_timeout = '600s'"),
        ]
        assert sess_obj.rollback.calls == [pretend.call()]
        assert sess_obj.close.calls == [pretend.call()]
        assert es_client.indices.indices == {}

    def test_successfully_indexes_and_adds_new(self, monkeypatch, cli):
        sess_obj = pretend.stub(
            execute=pretend.call_recorder(lambda q: None),
            rollback=pretend.call_recorder(lambda: None),
            close=pretend.call_recorder(lambda: None),
        )
        sess_cls = pretend.call_recorder(lambda bind: sess_obj)
        monkeypatch.setattr(warehouse.cli.search.reindex, "Session", sess_cls)

        docs = pretend.stub()

        def project_docs(db):
            return docs

        monkeypatch.setattr(
            warehouse.cli.search.reindex,
            "_project_docs",
            project_docs,
        )

        es_client = FakeESClient()
        db_engine = pretend.stub()

        config = pretend.stub(
            registry={
                "elasticsearch.client": es_client,
                "elasticsearch.index": "warehouse",
                "sqlalchemy.engine": db_engine,
            },
        )

        bulk = pretend.call_recorder(lambda client, iterable: None)
        monkeypatch.setattr(warehouse.cli.search.reindex, "bulk", bulk)

        monkeypatch.setattr(os, "urandom", lambda n: b"\xcb" * n)

        result = cli.invoke(reindex, obj=config)

        assert result.exit_code == 0
        assert sess_cls.calls == [pretend.call(bind=db_engine)]
        assert sess_obj.execute.calls == [
            pretend.call(
                """ BEGIN TRANSACTION
                ISOLATION LEVEL SERIALIZABLE
                READ ONLY
                DEFERRABLE
            """
            ),
            pretend.call("SET statement_timeout = '600s'"),
        ]
        assert bulk.calls == [pretend.call(es_client, docs)]
        assert sess_obj.rollback.calls == [pretend.call()]
        assert sess_obj.close.calls == [pretend.call()]
        assert set(es_client.indices.indices) == {"warehouse-cbcbcbcbcb"}
        assert es_client.indices.aliases == {
            "warehouse": ["warehouse-cbcbcbcbcb"],
        }

    def test_successfully_indexes_and_replaces(self, monkeypatch, cli):
        sess_obj = pretend.stub(
            execute=pretend.call_recorder(lambda q: None),
            rollback=pretend.call_recorder(lambda: None),
            close=pretend.call_recorder(lambda: None),
        )
        sess_cls = pretend.call_recorder(lambda bind: sess_obj)
        monkeypatch.setattr(warehouse.cli.search.reindex, "Session", sess_cls)

        docs = pretend.stub()

        def project_docs(db):
            return docs

        monkeypatch.setattr(
            warehouse.cli.search.reindex,
            "_project_docs",
            project_docs,
        )

        es_client = FakeESClient()
        es_client.indices.indices["warehouse-aaaaaaaaaa"] = None
        es_client.indices.aliases["warehouse"] = ["warehouse-aaaaaaaaaa"]
        db_engine = pretend.stub()

        config = pretend.stub(
            registry={
                "elasticsearch.client": es_client,
                "elasticsearch.index": "warehouse",
                "sqlalchemy.engine": db_engine,
            },
        )

        bulk = pretend.call_recorder(lambda client, iterable: None)
        monkeypatch.setattr(warehouse.cli.search.reindex, "bulk", bulk)

        monkeypatch.setattr(os, "urandom", lambda n: b"\xcb" * n)

        result = cli.invoke(reindex, obj=config)

        assert result.exit_code == 0
        assert sess_cls.calls == [pretend.call(bind=db_engine)]
        assert sess_obj.execute.calls == [
            pretend.call(
                """ BEGIN TRANSACTION
                ISOLATION LEVEL SERIALIZABLE
                READ ONLY
                DEFERRABLE
            """
            ),
            pretend.call("SET statement_timeout = '600s'"),
        ]
        assert bulk.calls == [pretend.call(es_client, docs)]
        assert sess_obj.rollback.calls == [pretend.call()]
        assert sess_obj.close.calls == [pretend.call()]
        assert set(es_client.indices.indices) == {"warehouse-cbcbcbcbcb"}
        assert es_client.indices.aliases == {
            "warehouse": ["warehouse-cbcbcbcbcb"],
        }
