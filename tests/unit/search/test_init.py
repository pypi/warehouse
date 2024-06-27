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

import opensearchpy
import pretend

from warehouse import search

from ...common.db.packaging import ProjectFactory, ReleaseFactory


def test_store_projects(db_request):
    project0 = ProjectFactory.create()
    project1 = ProjectFactory.create()
    release1 = ReleaseFactory.create(project=project1)
    config = pretend.stub()
    session = pretend.stub(info={}, new={project0}, dirty=set(), deleted={release1})

    search.store_projects_for_project_reindex(config, session, pretend.stub())

    assert session.info["warehouse.search.project_updates"] == {project0, project1}
    assert session.info["warehouse.search.project_deletes"] == set()


def test_store_projects_unindex(db_request):
    project0 = ProjectFactory.create()
    project1 = ProjectFactory.create()
    config = pretend.stub()
    session = pretend.stub(info={}, new={project0}, dirty=set(), deleted={project1})

    search.store_projects_for_project_reindex(config, session, pretend.stub())

    assert session.info["warehouse.search.project_updates"] == {project0}
    assert session.info["warehouse.search.project_deletes"] == {project1}


def test_execute_reindex_success(app_config):
    _delay = pretend.call_recorder(lambda x: None)
    app_config.task = lambda x: pretend.stub(delay=_delay)
    session = pretend.stub(
        info={"warehouse.search.project_updates": {pretend.stub(normalized_name="foo")}}
    )

    search.execute_project_reindex(app_config, session)

    assert _delay.calls == [pretend.call("foo")]
    assert "warehouse.search.project_updates" not in session.info


def test_execute_unindex_success(app_config):
    _delay = pretend.call_recorder(lambda x: None)
    app_config.task = lambda x: pretend.stub(delay=_delay)
    session = pretend.stub(
        info={"warehouse.search.project_deletes": {pretend.stub(normalized_name="foo")}}
    )

    search.execute_project_reindex(app_config, session)

    assert _delay.calls == [pretend.call("foo")]
    assert "warehouse.search.project_deletes" not in session.info


def test_opensearch(monkeypatch):
    search_obj = pretend.stub()
    index_obj = pretend.stub(
        document=pretend.call_recorder(lambda d: None),
        search=pretend.call_recorder(lambda: search_obj),
        settings=pretend.call_recorder(lambda **kw: None),
    )
    index_cls = pretend.call_recorder(lambda name, using: index_obj)
    monkeypatch.setattr(search.utils, "Index", index_cls)

    doc_types = [pretend.stub(), pretend.stub()]

    client = pretend.stub()
    request = pretend.stub(
        registry={
            "opensearch.client": client,
            "opensearch.index": "warehouse",
            "search.doc_types": doc_types,
        }
    )

    opensearch = search.opensearch(request)

    assert opensearch is search_obj
    assert index_cls.calls == [pretend.call("warehouse", using=client)]
    assert index_obj.document.calls == [pretend.call(d) for d in doc_types]
    assert index_obj.settings.calls == [
        pretend.call(number_of_shards=1, number_of_replicas=0, refresh_interval="1s")
    ]
    assert index_obj.search.calls == [pretend.call()]


def test_includeme(monkeypatch):
    aws4auth_stub = pretend.stub()
    aws4auth = pretend.call_recorder(lambda *a, **kw: aws4auth_stub)
    opensearch_client = pretend.stub()
    opensearch_client_init = pretend.call_recorder(lambda *a, **kw: opensearch_client)

    monkeypatch.setattr(search.requests_aws4auth, "AWS4Auth", aws4auth)
    monkeypatch.setattr(search.opensearchpy, "OpenSearch", opensearch_client_init)

    registry = {}
    opensearch_url = "https://some.url/some-index?aws_auth=1&region=us-east-2"
    config = pretend.stub(
        registry=pretend.stub(
            settings={
                "aws.key_id": "AAAAAAAAAAAA",
                "aws.secret_key": "deadbeefdeadbeefdeadbeef",
                "opensearch.url": opensearch_url,
            },
            __setitem__=registry.__setitem__,
        ),
        add_request_method=pretend.call_recorder(lambda *a, **kw: None),
        add_periodic_task=pretend.call_recorder(lambda *a, **kw: None),
    )

    search.includeme(config)

    assert aws4auth.calls == [
        pretend.call("AAAAAAAAAAAA", "deadbeefdeadbeefdeadbeef", "us-east-2", "es")
    ]
    assert len(opensearch_client_init.calls) == 1
    assert opensearch_client_init.calls[0].kwargs["hosts"] == ["https://some.url"]
    assert opensearch_client_init.calls[0].kwargs["timeout"] == 2
    assert opensearch_client_init.calls[0].kwargs["retry_on_timeout"] is False
    assert (
        opensearch_client_init.calls[0].kwargs["connection_class"]
        == opensearchpy.connection.http_requests.RequestsHttpConnection
    )
    assert opensearch_client_init.calls[0].kwargs["http_auth"] == aws4auth_stub

    assert registry["opensearch.client"] == opensearch_client
    assert registry["opensearch.index"] == "some-index"
    assert registry["opensearch.shards"] == 1
    assert registry["opensearch.replicas"] == 0
    assert config.add_request_method.calls == [
        pretend.call(search.opensearch, name="opensearch", reify=True)
    ]
