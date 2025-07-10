# SPDX-License-Identifier: Apache-2.0

import pretend

from warehouse.cli.storages import reconcile
from warehouse.packaging.tasks import (
    reconcile_file_storages as _reconcile_file_storages,
)


class TestCLIStorages:
    def test_reindex(self, cli):
        request = pretend.stub(
            registry=pretend.stub(settings={"reconcile_file_storages.batch_size": 1000})
        )
        task = pretend.stub(
            get_request=pretend.call_recorder(lambda *a, **kw: request),
            run=pretend.call_recorder(lambda *a, **kw: None),
        )
        config = pretend.stub(task=pretend.call_recorder(lambda *a, **kw: task))

        result = cli.invoke(reconcile, obj=config)

        assert result.exit_code == 0
        assert config.task.calls == [
            pretend.call(_reconcile_file_storages),
            pretend.call(_reconcile_file_storages),
        ]
        assert task.get_request.calls == [pretend.call()]
        assert task.run.calls == [pretend.call(request)]
