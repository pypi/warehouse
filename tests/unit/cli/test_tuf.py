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

import pretend

from warehouse.cli import tuf


class TestTufCLI:
    def test_keypair(self, monkeypatch, cli):
        response = pretend.stub(raise_for_status=pretend.call_recorder(lambda: None))
        client = pretend.stub(
            secrets=pretend.stub(
                transit=pretend.stub(
                    create_key=pretend.call_recorder(lambda **kw: response),
                    read_key=pretend.call_recorder(lambda **kw: "fake key info"),
                )
            )
        )
        vault = pretend.call_recorder(lambda c: client)
        monkeypatch.setattr(tuf, "_vault", vault)

        config = pretend.stub()

        result = cli.invoke(tuf.keypair, ["--rolename", "root"], obj=config)

        assert result.exit_code == 0
        assert vault.calls == [pretend.call(config)]
        assert client.secrets.transit.create_key.calls == [
            pretend.call(name="root", exportable=False, key_type="ed25519")
        ]
        assert client.secrets.transit.read_key.calls == [pretend.call(name="root")]
        assert response.raise_for_status.calls == [pretend.call()]
