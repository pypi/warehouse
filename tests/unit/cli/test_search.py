# SPDX-License-Identifier: Apache-2.0

import types

from opensearchpy.exceptions import NotFoundError

from warehouse.cli.search import delete_older_indices, print_indices, reindex
from warehouse.search.tasks import reindex as _reindex
from warehouse.tasks import WarehouseTask


class TestCLISearch:
    def test_reindex(self, cli, mocker):
        task = mocker.create_autospec(WarehouseTask, instance=True)
        config = mocker.Mock()
        config.task.return_value = task

        result = cli.invoke(reindex, obj=config)

        assert result.exit_code == 0
        assert config.task.call_args_list == [
            mocker.call(_reindex),
            mocker.call(_reindex),
        ]
        task.get_request.assert_called_once_with()
        task.run.assert_called_once_with(task.get_request.return_value)

    def test_print_indices(self, cli, mocker):
        # Mock the OpenSearch client responses
        client = mocker.Mock()
        client.cat.indices.return_value = "health status index id pri rep docs.count docs.deleted store.size creation.date.string\ngreen  open   production-2024-01-01 abc 1 0 1000 0 1mb 2024-01-01T00:00:00Z"  # noqa: E501
        client.indices.get_alias.return_value = {
            "production-2024-01-01": {"aliases": {"production": {}}},
            "staging-2024-01-01": {"aliases": {"staging": {}}},
        }
        config = types.SimpleNamespace(registry={"opensearch.client": client})

        result = cli.invoke(print_indices, obj=config)

        assert result.exit_code == 0
        # Check that cat.indices was called with correct parameters
        client.cat.indices.assert_called_once_with(
            index="production*,staging*",
            h="health,status,index,id,pri,rep,docs.count,docs.deleted,store.size,creation.date.string",
            s="creation.date.string:desc",
            v=True,
        )
        # Check that indices.get_alias was called
        client.indices.get_alias.assert_called_once_with(index="production*,staging*")
        # Check output contains expected content
        assert "health status index" in result.output
        assert "Current Aliases:" in result.output
        assert "production -> production-2024-01-01" in result.output
        assert "staging -> staging-2024-01-01" in result.output

    def test_delete_older_indices_success(self, cli, mocker):
        # Mock OpenSearch client with multiple indices
        # Keep latest 2: production-2024-03-01 + production-2024-02-01
        # Delete: production-2024-01-01
        client = mocker.Mock()
        client.indices.get_alias.return_value = {
            "production-2024-03-01": {"aliases": {"production": {}}}
        }
        client.indices.get.return_value = {
            "production-2024-03-01": {},
            "production-2024-02-01": {},
            "production-2024-01-01": {},
        }
        client.indices.delete.return_value = {"acknowledged": True}
        config = types.SimpleNamespace(registry={"opensearch.client": client})

        result = cli.invoke(delete_older_indices, ["production"], obj=config)

        assert result.exit_code == 0
        # Check that get_alias was called correctly
        client.indices.get_alias.assert_called_once_with(name="production")
        # Check that get was called to fetch all indices
        client.indices.get.assert_called_once_with(index="production-*")
        # Check that delete was called only for the oldest index (keeps latest 2)
        client.indices.delete.assert_called_once_with(index="production-2024-01-01")
        # Check output
        assert "Current index: production-2024-03-01" in result.output
        assert "Found 1 older indices to delete." in result.output
        assert "Deleting index: production-2024-01-01" in result.output
        assert "Done." in result.output

    def test_delete_older_indices_multiple_deletions(self, cli, mocker):
        # Mock OpenSearch client with many indices
        # Keep latest 2: production-2024-05-01 + production-2024-04-01
        # Delete: production-2024-03-01, production-2024-02-01, production-2024-01-01
        client = mocker.Mock()
        client.indices.get_alias.return_value = {
            "production-2024-04-01": {"aliases": {"production": {}}}
        }
        client.indices.get.return_value = {
            "production-2024-05-01": {},
            "production-2024-04-01": {},
            "production-2024-03-01": {},
            "production-2024-02-01": {},
            "production-2024-01-01": {},
        }
        client.indices.delete.return_value = {"acknowledged": True}
        config = types.SimpleNamespace(registry={"opensearch.client": client})

        result = cli.invoke(delete_older_indices, ["production"], obj=config)

        assert result.exit_code == 0
        # Check that delete was called for all old indices (keeps latest 2)
        assert client.indices.delete.call_args_list == [
            mocker.call(index="production-2024-03-01"),
            mocker.call(index="production-2024-02-01"),
            mocker.call(index="production-2024-01-01"),
        ]
        # Check output
        assert "Current index: production-2024-04-01" in result.output
        assert "Found 3 older indices to delete." in result.output
        assert "Done." in result.output

    def test_delete_older_indices_no_alias(self, cli, mocker):
        # Mock OpenSearch client to raise NotFoundError when alias not found
        client = mocker.Mock()
        client.indices.get_alias.side_effect = NotFoundError(
            404, "index_not_found_exception", "no such index"
        )
        config = types.SimpleNamespace(registry={"opensearch.client": client})

        result = cli.invoke(delete_older_indices, ["production"], obj=config)

        assert result.exit_code == 1
        # Check that get_alias was called
        client.indices.get_alias.assert_called_once_with(name="production")
        # Check error message
        assert "No alias found for production, aborting." in result.output

    def test_delete_older_indices_only_current(self, cli, mocker):
        # Mock OpenSearch client with only the current index (no backup, no older)
        client = mocker.Mock()
        client.indices.get_alias.return_value = {
            "production-2024-03-01": {"aliases": {"production": {}}}
        }
        client.indices.get.return_value = {"production-2024-03-01": {}}
        client.indices.delete.return_value = {"acknowledged": True}
        config = types.SimpleNamespace(registry={"opensearch.client": client})

        result = cli.invoke(delete_older_indices, ["production"], obj=config)

        assert result.exit_code == 0
        # Check that delete was never called (only 1 index exists)
        client.indices.delete.assert_not_called()
        # Check output
        assert "Current index: production-2024-03-01" in result.output
        assert "Found 0 older indices to delete." in result.output
        assert "Done." in result.output

    def test_delete_older_indices_keeps_two(self, cli, mocker):
        # Mock OpenSearch client with exactly 2 indices (current + 1 backup)
        # Should not delete anything - keeps both
        client = mocker.Mock()
        client.indices.get_alias.return_value = {
            "production-2024-02-01": {"aliases": {"production": {}}}
        }
        client.indices.get.return_value = {
            "production-2024-02-01": {},
            "production-2024-01-01": {},
        }
        client.indices.delete.return_value = {"acknowledged": True}
        config = types.SimpleNamespace(registry={"opensearch.client": client})

        result = cli.invoke(delete_older_indices, ["production"], obj=config)

        assert result.exit_code == 0
        # Check that delete was never called (keeps latest 2)
        client.indices.delete.assert_not_called()
        # Check output
        assert "Current index: production-2024-02-01" in result.output
        assert "Found 0 older indices to delete." in result.output
        assert "Done." in result.output
