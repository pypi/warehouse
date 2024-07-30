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
