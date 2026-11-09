# SPDX-License-Identifier: Apache-2.0

import json

import pytest
import responses

from warehouse import tuf


class TestTUF:
    server = "https://rstuf.api"
    task_id = "123456"

    @responses.activate
    def test_get_task_state(self):
        state = "SUCCESS"
        responses.get(
            f"{self.server}/api/v1/task?task_id={self.task_id}",
            json={"data": {"state": state}},
        )

        result = tuf.get_task_state(self.server, self.task_id)

        assert result == state
        assert len(responses.calls) == 1
        assert responses.calls[0].request.req_kwargs["timeout"] == 5

    @responses.activate
    def test_post_bootstrap(self):
        payload = ["foo"]
        responses.post(
            f"{self.server}/api/v1/bootstrap", json={"data": {"task_id": self.task_id}}
        )

        result = tuf.post_bootstrap(self.server, payload)

        assert result == self.task_id
        assert len(responses.calls) == 1
        assert json.loads(responses.calls[0].request.body) == payload
        assert responses.calls[0].request.req_kwargs["timeout"] == 5

    @responses.activate
    def test_post_bootstrap_incomplete_response(self):
        """RSTUF can answer 200 without a ``data`` key when the job fails."""
        responses.post(f"{self.server}/api/v1/bootstrap", json={"error": "nope"})

        with pytest.raises(tuf.RSTUFError) as excinfo:
            tuf.post_bootstrap(self.server, ["foo"])

        assert str(excinfo.value) == "Error in RSTUF job: {'error': 'nope'}"
        assert len(responses.calls) == 1

    def test_wait_for_success(self, mocker):
        get_task_state = mocker.patch.object(
            tuf, "get_task_state", autospec=True, return_value="SUCCESS"
        )
        tuf.wait_for_success(self.server, self.task_id)

        get_task_state.assert_called_once_with(self.server, self.task_id)

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
    def test_wait_for_success_error(self, state, iterations, mocker):
        mocker.patch.object(tuf, "time", autospec=True)

        get_task_state = mocker.patch.object(
            tuf, "get_task_state", autospec=True, return_value=state
        )

        with pytest.raises(tuf.RSTUFError):
            tuf.wait_for_success(self.server, self.task_id)

        assert (
            get_task_state.call_args_list
            == [mocker.call(self.server, self.task_id)] * iterations
        )
        pending = state in {"PENDING", "RUNNING", "RECEIVED", "STARTED"}
        sleeps = iterations if pending else 0
        assert tuf.time.sleep.call_args_list == [mocker.call(1)] * sleeps
