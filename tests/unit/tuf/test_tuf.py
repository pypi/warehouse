# SPDX-License-Identifier: Apache-2.0

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

    def test_wait_for_success(self, monkeypatch):
        get_task_state = call_recorder(lambda *a: "SUCCESS")
        monkeypatch.setattr(tuf, "get_task_state", get_task_state)
        tuf.wait_for_success(self.server, self.task_id)

        assert get_task_state.calls == [call(self.server, self.task_id)]

    @pytest.mark.parametrize(
        ("state", "iterations"),
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
