# SPDX-License-Identifier: Apache-2.0

import types

import opensearchpy

from warehouse import search
from warehouse.packaging.models import Project

from ...common.db.packaging import ProjectFactory, ReleaseFactory


def test_store_projects(db_request, mocker):
    project0 = ProjectFactory.create()
    project1 = ProjectFactory.create()
    project3 = ProjectFactory.create(lifecycle_status="archived-noindex")
    release1 = ReleaseFactory.create(project=project1)
    session = types.SimpleNamespace(
        info={}, new={project0}, dirty={project3}, deleted={release1}
    )

    search.store_projects_for_project_reindex(
        mocker.sentinel.config, session, mocker.sentinel.flush_context
    )

    assert session.info["warehouse.search.project_updates"] == {project0, project1}
    assert session.info["warehouse.search.project_deletes"] == {project3}


def test_store_projects_unindex(db_request, mocker):
    project0 = ProjectFactory.create()
    project1 = ProjectFactory.create()
    session = types.SimpleNamespace(
        info={}, new={project0}, dirty=set(), deleted={project1}
    )

    search.store_projects_for_project_reindex(
        mocker.sentinel.config, session, mocker.sentinel.flush_context
    )

    assert session.info["warehouse.search.project_updates"] == {project0}
    assert session.info["warehouse.search.project_deletes"] == {project1}


def test_execute_reindex_success(app_config, mocker):
    delay = mocker.stub(name="delay")
    app_config.task = lambda x: types.SimpleNamespace(delay=delay)
    session = types.SimpleNamespace(
        info={
            "warehouse.search.project_updates": {
                Project(name="foo", normalized_name="foo")
            }
        }
    )

    search.execute_project_reindex(app_config, session)

    delay.assert_called_once_with("foo")
    assert "warehouse.search.project_updates" not in session.info


def test_execute_unindex_success(app_config, mocker):
    delay = mocker.stub(name="delay")
    app_config.task = lambda x: types.SimpleNamespace(delay=delay)
    session = types.SimpleNamespace(
        info={
            "warehouse.search.project_deletes": {
                Project(name="foo", normalized_name="foo")
            }
        }
    )

    search.execute_project_reindex(app_config, session)

    delay.assert_called_once_with("foo")
    assert "warehouse.search.project_deletes" not in session.info


def test_opensearch(mocker):
    search_obj = mocker.sentinel.search_obj
    index_obj = mocker.Mock(spec=["document", "search", "settings"])
    index_obj.search.return_value = search_obj
    index_cls = mocker.patch.object(search.utils, "Index", return_value=index_obj)

    doc_types = [mocker.sentinel.doc0, mocker.sentinel.doc1]
    client = mocker.sentinel.client
    request = types.SimpleNamespace(
        registry={
            "opensearch.client": client,
            "opensearch.index": "warehouse",
            "search.doc_types": doc_types,
        }
    )

    assert search.opensearch(request) is search_obj
    index_cls.assert_called_once_with("warehouse", using=client)
    assert index_obj.document.call_args_list == [mocker.call(d) for d in doc_types]
    index_obj.settings.assert_called_once_with(
        number_of_shards=1, number_of_replicas=0, refresh_interval="1s"
    )
    index_obj.search.assert_called_once_with()


def test_includeme(mocker):
    signer_auth = mocker.patch.object(
        search, "RequestsAWSV4SignerAuth", return_value=mocker.sentinel.signer_auth
    )
    credentials = mocker.patch.object(
        search, "Credentials", return_value=mocker.sentinel.credentials
    )
    opensearch_client_init = mocker.patch.object(
        search.opensearchpy,
        "OpenSearch",
        return_value=mocker.sentinel.opensearch_client,
    )

    opensearch_url = "https://some.url/some-index?aws_auth=1&region=us-east-2"

    class Registry(dict):
        settings = {
            "aws.key_id": "AAAAAAAAAAAA",
            "aws.secret_key": "deadbeefdeadbeefdeadbeef",
            "opensearch.url": opensearch_url,
            "warehouse.search.ratelimit_string": "10 per second",
        }

    registry = Registry()
    config = mocker.Mock(
        spec=[
            "registry",
            "add_request_method",
            "add_periodic_task",
            "register_service_factory",
            "register_rate_limiter",
        ]
    )
    config.registry = registry

    search.includeme(config)

    credentials.assert_called_once_with(
        access_key="AAAAAAAAAAAA", secret_key="deadbeefdeadbeefdeadbeef"
    )
    signer_auth.assert_called_once_with(mocker.sentinel.credentials, "us-east-2", "es")
    assert opensearch_client_init.call_count == 1
    kwargs = opensearch_client_init.call_args.kwargs
    assert kwargs["hosts"] == ["https://some.url"]
    assert kwargs["timeout"] == 1
    assert kwargs["retry_on_timeout"] is True
    assert kwargs["max_retries"] == 1
    assert (
        kwargs["connection_class"]
        == opensearchpy.connection.http_requests.RequestsHttpConnection
    )
    assert kwargs["http_auth"] == mocker.sentinel.signer_auth

    assert registry["opensearch.client"] == mocker.sentinel.opensearch_client
    assert registry["opensearch.index"] == "some-index"
    assert registry["opensearch.shards"] == 1
    assert registry["opensearch.replicas"] == 0
    config.add_request_method.assert_called_once_with(
        search.opensearch, name="opensearch", reify=True
    )
    config.register_rate_limiter.assert_called_once_with("10 per second", "search")
    config.register_service_factory.assert_called_once_with(
        search.services.SearchService.create_service,
        iface=search.interfaces.ISearchService,
    )


def test_execute_reindex_no_service(mocker):
    config = mocker.Mock(spec=["find_service_factory"])
    config.find_service_factory.side_effect = LookupError

    search.execute_project_reindex(config, mocker.sentinel.session)

    config.find_service_factory.assert_called_once_with(
        search.interfaces.ISearchService
    )
