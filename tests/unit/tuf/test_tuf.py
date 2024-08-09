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

import pytest

from pretend import call, call_recorder, stub

from warehouse import tuf


class TestTUF:
    server = "rstuf.api"
    task_id = "123456"

    def test_get_task_state(self, monkeypatch):
        state = "SUCCESS"

        resp_json = {"data": {"state": state}}
        resp = stub(
            raise_for_status=(lambda *a: None), json=(lambda *a, **kw: resp_json)
        )
        get = call_recorder(lambda *a: resp)
        monkeypatch.setattr(tuf.requests, "get", get)

        result = tuf.get_task_state(self.server, self.task_id)

        assert result == state
        assert get.calls == [call(f"{self.server}/api/v1/task?task_id={self.task_id}")]

    def test_post_bootstrap(self, monkeypatch):
        payload = ["foo"]

        resp_json = {"data": {"task_id": self.task_id}}
        resp = stub(
            raise_for_status=(lambda *a: None), json=(lambda *a, **kw: resp_json)
        )
        post = call_recorder(lambda *a, **kw: resp)
        monkeypatch.setattr(tuf.requests, "post", post)

        # Test success
        result = tuf.post_bootstrap(self.server, payload)

        assert result == self.task_id
        assert post.calls == [call(f"{self.server}/api/v1/bootstrap", json=payload)]

        # Test fail with incomplete response json
        del resp_json["data"]
        with pytest.raises(tuf.RSTUFError):
            tuf.post_bootstrap(self.server, payload)

    def test_post_artifacts(self, monkeypatch):
        payload = {
            "targets": [
                {
                    "path": "foo",
                    "info": {
                        "length": 42,
                        "hashes": {"blake2b-256": "deadbeef"},
                    },
                }
            ]
        }

        resp_json = {"data": {"task_id": self.task_id}}
        resp = stub(
            raise_for_status=(lambda *a: None), json=(lambda *a, **kw: resp_json)
        )
        post = call_recorder(lambda *a, **kw: resp)
        monkeypatch.setattr(tuf.requests, "post", post)

        # Test success
        result = tuf.post_artifacts(self.server, payload)

        assert result == self.task_id
        assert post.calls == [call(f"{self.server}/api/v1/artifacts", json=payload)]

        # Test fail with incomplete response json (i.e. no bootstrap error)
        del resp_json["data"]
        with pytest.raises(tuf.RSTUFNoBootstrapError):
            tuf.post_artifacts(self.server, payload)

    def test_wait_for_success(self, monkeypatch):
        get_task_state = call_recorder(lambda *a: "SUCCESS")
        monkeypatch.setattr(tuf, "get_task_state", get_task_state)
        tuf.wait_for_success(self.server, self.task_id)

        assert get_task_state.calls == [call(self.server, self.task_id)]

    @pytest.mark.parametrize(
        "state, iterations",
        [
            ("PENDING", 20),
            ("RUNNING", 20),
            ("RECEIVED", 20),
            ("STARTED", 20),
            ("FAILURE", 1),
            ("ERRORED", 1),
            ("REVOKED", 1),
            ("REJECTED", 1),
            ("bogus", 1),
        ],
    )
    def test_wait_for_success_error(self, state, iterations, monkeypatch):
        monkeypatch.setattr(tuf.time, "sleep", lambda *a: None)

        get_task_state = call_recorder(lambda *a: state)
        monkeypatch.setattr(tuf, "get_task_state", get_task_state)

        with pytest.raises(tuf.RSTUFError):
            tuf.wait_for_success(self.server, self.task_id)

        assert get_task_state.calls == [call(self.server, self.task_id)] * iterations

    def test_update_metadata(self, db_request, monkeypatch):
        project_id = "id"
        project_name = "name"

        project = stub(normalized_name=project_name)

        one = call_recorder(lambda: project)
        db_request.db.query = lambda a: stub(filter=lambda a: stub(one=one))

        # Test early return, if no RSTUF API URL configured
        db_request.registry.settings = {"tuf.rstuf_api_url": None}
        tuf.update_metadata(db_request, project_id)

        assert not one.calls

        # Test regular run
        rstuf_url = "url"
        index_digest = "digest"
        index_size = 42

        db_request.registry.settings = {"tuf.rstuf_api_url": rstuf_url}

        render = call_recorder(lambda *a, **kw: (index_digest, None, index_size))
        monkeypatch.setattr(tuf, "render_simple_detail", render)

        post = call_recorder(lambda *a: self.task_id)
        monkeypatch.setattr(tuf, "post_artifacts", post)

        wait = call_recorder(lambda *a: None)
        monkeypatch.setattr(tuf, "wait_for_success", wait)

        tuf.update_metadata(db_request, project_id)
        assert one.calls == [call()]
        assert render.calls == [call(project, db_request, store=True)]
        assert post.calls == [
            call(
                rstuf_url,
                {
                    "targets": [
                        {
                            "path": project_name,
                            "info": {
                                "length": index_size,
                                "hashes": {"blake2b-256": index_digest},
                            },
                        }
                    ]
                },
            )
        ]
        assert wait.calls == [call(rstuf_url, self.task_id)]
