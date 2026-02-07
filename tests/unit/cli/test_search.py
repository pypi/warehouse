# SPDX-License-Identifier: Apache-2.0

import pretend

from opensearchpy.exceptions import NotFoundError

from warehouse.cli.search import delete_older_indices, print_indices, reindex
from warehouse.search.tasks import reindex as _reindex


class TestCLISearch:
    def test_reindex(self, cli):
        request = pretend.stub()
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.call_recorder(lambda *a, **kw: None),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        result = cli.invoke(reindex, obj=config)

        assert result.exit_code == 0
        assert config.task.calls == [pretend.call(_reindex), pretend.call(_reindex)]
        assert task.get_request.calls == [pretend.call()]
        assert task.run.calls == [pretend.call(request)]

    def test_print_indices(self, cli):
        # Mock the OpenSearch client responses
        cat_client = pretend.stub(
            indices=pretend.call_recorder(
                lambda **kw: "health status index id pri rep docs.count docs.deleted store.size creation.date.string\ngreen  open   production-2024-01-01 abc 1 0 1000 0 1mb 2024-01-01T00:00:00Z"  # noqa: E501
            )
        )
        indices_client = pretend.stub(
            get_alias=pretend.call_recorder(
                lambda **kw: {
                    "production-2024-01-01": {"aliases": {"production": {}}},
                    "staging-2024-01-01": {"aliases": {"staging": {}}},
                }
            )
        )
        client = pretend.stub(cat=cat_client, indices=indices_client)
        config = pretend.stub(registry={"opensearch.client": client})

        result = cli.invoke(print_indices, obj=config)

        assert result.exit_code == 0
        # Check that cat.indices was called with correct parameters
        assert cat_client.indices.calls == [
            pretend.call(
                index="production*,staging*",
                h="health,status,index,id,pri,rep,docs.count,docs.deleted,store.size,creation.date.string",  # noqa: E501
                s="creation.date.string:desc",
                v=True,
            )
        ]
        # Check that indices.get_alias was called
        assert indices_client.get_alias.calls == [
            pretend.call(index="production*,staging*")
        ]
        # Check output contains expected content
        assert "health status index" in result.output
        assert "Current Aliases:" in result.output
        assert "production -> production-2024-01-01" in result.output
        assert "staging -> staging-2024-01-01" in result.output

    def test_delete_older_indices_success(self, cli):
        # Mock OpenSearch client with multiple indices
        # Keep latest 2: production-2024-03-01 + production-2024-02-01
        # Delete: production-2024-01-01
        indices_client = pretend.stub(
            get_alias=pretend.call_recorder(
                lambda **kw: {"production-2024-03-01": {"aliases": {"production": {}}}}
            ),
            get=pretend.call_recorder(
                lambda **kw: {
                    "production-2024-03-01": {},
                    "production-2024-02-01": {},
                    "production-2024-01-01": {},
                }
            ),
            delete=pretend.call_recorder(lambda **kw: {"acknowledged": True}),
        )
        client = pretend.stub(indices=indices_client)
        config = pretend.stub(registry={"opensearch.client": client})

        result = cli.invoke(delete_older_indices, ["production"], obj=config)

        assert result.exit_code == 0
        # Check that get_alias was called correctly
        assert indices_client.get_alias.calls == [pretend.call(name="production")]
        # Check that get was called to fetch all indices
        assert indices_client.get.calls == [pretend.call(index="production-*")]
        # Check that delete was called only for the oldest index (keeps latest 2)
        assert indices_client.delete.calls == [
            pretend.call(index="production-2024-01-01"),
        ]
        # Check output
        assert "Current index: production-2024-03-01" in result.output
        assert "Found 1 older indices to delete." in result.output
        assert "Deleting index: production-2024-01-01" in result.output
        assert "Done." in result.output

    def test_delete_older_indices_multiple_deletions(self, cli):
        # Mock OpenSearch client with many indices
        # Keep latest 2: production-2024-05-01 + production-2024-04-01
        # Delete: production-2024-03-01, production-2024-02-01, production-2024-01-01
        indices_client = pretend.stub(
            get_alias=pretend.call_recorder(
                lambda **kw: {"production-2024-04-01": {"aliases": {"production": {}}}}
            ),
            get=pretend.call_recorder(
                lambda **kw: {
                    "production-2024-05-01": {},
                    "production-2024-04-01": {},
                    "production-2024-03-01": {},
                    "production-2024-02-01": {},
                    "production-2024-01-01": {},
                }
            ),
            delete=pretend.call_recorder(lambda **kw: {"acknowledged": True}),
        )
        client = pretend.stub(indices=indices_client)
        config = pretend.stub(registry={"opensearch.client": client})

        result = cli.invoke(delete_older_indices, ["production"], obj=config)

        assert result.exit_code == 0
        # Check that delete was called for all old indices (keeps latest 2)
        assert indices_client.delete.calls == [
            pretend.call(index="production-2024-03-01"),
            pretend.call(index="production-2024-02-01"),
            pretend.call(index="production-2024-01-01"),
        ]
        # Check output
        assert "Current index: production-2024-04-01" in result.output
        assert "Found 3 older indices to delete." in result.output
        assert "Done." in result.output

    def test_delete_older_indices_no_alias(self, cli):
        # Mock OpenSearch client to raise NotFoundError when alias not found
        def raise_not_found(**kw):
            raise NotFoundError(404, "index_not_found_exception", "no such index")

        indices_client = pretend.stub(get_alias=pretend.call_recorder(raise_not_found))
        client = pretend.stub(indices=indices_client)
        config = pretend.stub(registry={"opensearch.client": client})

        result = cli.invoke(delete_older_indices, ["production"], obj=config)

        assert result.exit_code == 1
        # Check that get_alias was called
        assert indices_client.get_alias.calls == [pretend.call(name="production")]
        # Check error message
        assert "No alias found for production, aborting." in result.output

    def test_delete_older_indices_only_current(self, cli):
        # Mock OpenSearch client with only the current index (no backup, no older)
        indices_client = pretend.stub(
            get_alias=pretend.call_recorder(
                lambda **kw: {"production-2024-03-01": {"aliases": {"production": {}}}}
            ),
            get=pretend.call_recorder(lambda **kw: {"production-2024-03-01": {}}),
            delete=pretend.call_recorder(lambda **kw: {"acknowledged": True}),
        )
        client = pretend.stub(indices=indices_client)
        config = pretend.stub(registry={"opensearch.client": client})

        result = cli.invoke(delete_older_indices, ["production"], obj=config)

        assert result.exit_code == 0
        # Check that delete was never called (only 1 index exists)
        assert indices_client.delete.calls == []
        # Check output
        assert "Current index: production-2024-03-01" in result.output
        assert "Found 0 older indices to delete." in result.output
        assert "Done." in result.output

    def test_delete_older_indices_keeps_two(self, cli):
        # Mock OpenSearch client with exactly 2 indices (current + 1 backup)
        # Should not delete anything - keeps both
        indices_client = pretend.stub(
            get_alias=pretend.call_recorder(
                lambda **kw: {"production-2024-02-01": {"aliases": {"production": {}}}}
            ),
            get=pretend.call_recorder(
                lambda **kw: {
                    "production-2024-02-01": {},
                    "production-2024-01-01": {},
                }
            ),
            delete=pretend.call_recorder(lambda **kw: {"acknowledged": True}),
        )
        client = pretend.stub(indices=indices_client)
        config = pretend.stub(registry={"opensearch.client": client})

        result = cli.invoke(delete_older_indices, ["production"], obj=config)

        assert result.exit_code == 0
        # Check that delete was never called (keeps latest 2)
        assert indices_client.delete.calls == []
        # Check output
        assert "Current index: production-2024-02-01" in result.output
        assert "Found 0 older indices to delete." in result.output
        assert "Done." in result.output
