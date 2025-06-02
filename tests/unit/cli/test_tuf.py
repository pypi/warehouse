# SPDX-License-Identifier: Apache-2.0

import json

from pretend import call, call_recorder

from warehouse.cli import tuf


class TestTUF:
    def test_bootstrap(self, cli, monkeypatch):
        task_id = "123456"
        server = "rstuf.api"
        payload = ["foo"]

        post = call_recorder(lambda *a: task_id)
        wait = call_recorder(lambda *a: None)
        monkeypatch.setattr(tuf, "post_bootstrap", post)
        monkeypatch.setattr(tuf, "wait_for_success", wait)

        result = cli.invoke(
            tuf.bootstrap, args=["--api-server", server, "-"], input=json.dumps(payload)
        )

        assert result.exit_code == 0

        assert post.calls == [call(server, payload)]
        assert wait.calls == [call(server, task_id)]
