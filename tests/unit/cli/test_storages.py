# SPDX-License-Identifier: Apache-2.0

from warehouse.cli.storages import reconcile
from warehouse.packaging.tasks import (
    reconcile_file_storages as _reconcile_file_storages,
)
from warehouse.tasks import WarehouseTask


class TestCLIStorages:
    def test_reindex(self, cli, mocker, pyramid_request):
        task = mocker.create_autospec(WarehouseTask, instance=True)
        task.get_request.return_value = pyramid_request
        config = mocker.Mock()
        config.task.return_value = task

        result = cli.invoke(reconcile, obj=config)

        assert result.exit_code == 0
        assert config.task.call_args_list == [
            mocker.call(_reconcile_file_storages),
            mocker.call(_reconcile_file_storages),
        ]
        task.get_request.assert_called_once_with()
        task.run.assert_called_once_with(pyramid_request)
