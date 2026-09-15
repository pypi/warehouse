# SPDX-License-Identifier: Apache-2.0

import json

from warehouse.cli import tuf


class TestTUF:
    def test_bootstrap(self, cli, mocker):
        task_id = "123456"
        server = "rstuf.api"
        payload = ["foo"]

        post = mocker.patch.object(
            tuf, "post_bootstrap", autospec=True, return_value=task_id
        )
        wait = mocker.patch.object(tuf, "wait_for_success", autospec=True)

        result = cli.invoke(
            tuf.bootstrap, args=["--api-server", server, "-"], input=json.dumps(payload)
        )

        assert result.exit_code == 0

        post.assert_called_once_with(server, payload)
        wait.assert_called_once_with(server, task_id)
