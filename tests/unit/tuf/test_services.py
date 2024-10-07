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
import pytest

from requests import Session
from zope.interface.verify import verifyClass

from warehouse.tuf import services
from warehouse.tuf.interfaces import ITUFService
from warehouse.tuf.services import RSTUFService


class TestRSTUFService:

    def test_verify_service(self):
        assert verifyClass(ITUFService, RSTUFService)

    def basic_init(self, db_request):
        db_request.registry.settings = {"rstuf.api_url": "http://rstuf"}

        rstuf = RSTUFService(db_request)

        assert rstuf is not None
        assert rstuf.api_url == "http://rstuf"
        assert isinstance(rstuf.requests, Session)

    def test_create_service(self, db_request):
        db_request.registry.settings = {"rstuf.api_url": "http://rstuf"}

        rstuf = RSTUFService.create_service(db_request)

        assert rstuf is not None
        assert rstuf.api_url == "http://rstuf"
        assert isinstance(rstuf.requests, Session)

    def test_get_task_state(self, monkeypatch, db_request):
        db_request.registry.settings = {"rstuf.api_url": "http://rstuf"}

        response = pretend.stub(
            raise_for_status=pretend.call_recorder(lambda: None),
            json=pretend.call_recorder(lambda: {"data": {"state": "SUCCESS"}}),
        )
        test_session = pretend.stub(
            get=pretend.call_recorder(lambda *a, **kw: response)
        )
        fake_session = pretend.call_recorder(lambda: test_session)
        monkeypatch.setattr(services, "Session", fake_session)

        rstuf = RSTUFService.create_service(db_request)

        state = rstuf.get_task_state("123456")

        assert state == "SUCCESS"

        assert test_session.get.calls == [
            pretend.call("http://rstuf/api/v1/task?task_id=123456"),
        ]
        assert response.raise_for_status.calls == [pretend.call()]
        assert response.json.calls == [pretend.call()]

    def test_post_artifacts(self, monkeypatch, db_request):
        db_request.registry.settings = {"rstuf.api_url": "http://rstuf"}

        response = pretend.stub(
            raise_for_status=pretend.call_recorder(lambda: None),
            json=pretend.call_recorder(lambda: {"data": {"task_id": "123456"}}),
        )
        test_session = pretend.stub(
            post=pretend.call_recorder(lambda *a, **kw: response)
        )
        fake_session = pretend.call_recorder(lambda: test_session)
        monkeypatch.setattr(services, "Session", fake_session)

        rstuf = RSTUFService.create_service(db_request)

        task_id = rstuf.post_artifacts({"targets": [{"path": "name"}]})

        assert task_id == "123456"

        assert test_session.post.calls == [
            pretend.call(
                "http://rstuf/api/v1/artifacts", json={"targets": [{"path": "name"}]}
            ),
        ]
        assert response.raise_for_status.calls == [pretend.call()]
        assert response.json.calls == [pretend.call()]

    @pytest.mark.parametrize(
        ("states", "exception", "message"),
        [
            (
                [
                    {"data": {"state": "PENDING"}},
                    {"data": {"state": "STARTED"}},
                    {"data": {"state": "RECEIVED"}},
                    {"data": {"state": "STARTED"}},
                    {"data": {"state": "SUCCESS"}},
                ],
                None,
                "",
            ),
            (
                [
                    {"data": {"state": "PENDING"}},
                    {"data": {"state": "STARTED"}},
                    {"data": {"state": "RECEIVED"}},
                    {"data": {"state": "STARTED"}},
                    {"data": {"state": "FAILURE"}},
                ],
                services.RSTUFError,
                "RSTUF job failed, please check payload and retry",
            ),
            (
                [
                    {"data": {"state": "PENDING"}},
                    {"data": {"state": "STARTED"}},
                    {"data": {"state": "RECEIVED"}},
                    {"data": {"state": "STARTED"}},
                    {"data": {"state": "ERRORED"}},
                ],
                services.RSTUFError,
                "RSTUF internal problem, please check RSTUF health",
            ),
            (
                [
                    {"data": {"state": "PENDING"}},
                    {"data": {"state": "STARTED"}},
                    {"data": {"state": "RECEIVED"}},
                    {"data": {"state": "STARTED"}},
                    {"data": {"state": "REVOKED"}},
                ],
                services.RSTUFError,
                "RSTUF internal problem, please check RSTUF health",
            ),
            (
                [
                    {"data": {"state": "PENDING"}},
                    {"data": {"state": "STARTED"}},
                    {"data": {"state": "RECEIVED"}},
                    {"data": {"state": "STARTED"}},
                    {"data": {"state": "REJECTED"}},
                ],
                services.RSTUFError,
                "RSTUF internal problem, please check RSTUF health",
            ),
            (
                [
                    {"data": {"state": "PENDING"}},
                    {"data": {"state": "STARTED"}},
                    {"data": {"state": "RECEIVED"}},
                    {"data": {"state": "STARTED"}},
                    {"data": {"state": "INVALID_STATE"}},
                ],
                services.RSTUFError,
                "RSTUF job returned unexpected state: INVALID_STATE",
            ),
            (
                [
                    {"data": {"state": "PENDING"}},
                    {"data": {"state": "PENDING"}},
                    {"data": {"state": "PENDING"}},
                    {"data": {"state": "PENDING"}},
                    {"data": {"state": "PENDING"}},
                ],
                services.RSTUFError,
                "RSTUF job failed, please check payload and retry",
            ),
        ],
    )
    def test_wait_for_pending_than_success(
        self, monkeypatch, db_request, states, exception, message
    ):
        db_request.registry.settings = {"rstuf.api_url": "http://rstuf"}

        # generate iter of responses
        responses = iter(states)
        response = pretend.stub(
            raise_for_status=pretend.call_recorder(lambda: None),
            json=pretend.call_recorder(lambda: next(responses)),
        )
        test_session = pretend.stub(
            get=pretend.call_recorder(lambda *a, **kw: response)
        )
        fake_session = pretend.call_recorder(lambda: test_session)
        monkeypatch.setattr(services, "Session", fake_session)

        rstuf = RSTUFService.create_service(db_request)
        rstuf.delay = 0.1  # speed up the test
        if message == "RSTUF job failed, please check payload and retry":
            rstuf.retries = 5  # simulate failure by limiting retries

        result = None
        if exception is not None:
            with pytest.raises(exception) as e:
                rstuf.wait_for_success("123456")

            assert message in str(e)
        else:
            result = rstuf.wait_for_success("123456")

        assert result is None

        assert test_session.get.calls == [
            pretend.call("http://rstuf/api/v1/task?task_id=123456"),
            pretend.call("http://rstuf/api/v1/task?task_id=123456"),
            pretend.call("http://rstuf/api/v1/task?task_id=123456"),
            pretend.call("http://rstuf/api/v1/task?task_id=123456"),
            pretend.call("http://rstuf/api/v1/task?task_id=123456"),
        ]
        assert response.raise_for_status.calls == [
            pretend.call(),
            pretend.call(),
            pretend.call(),
            pretend.call(),
            pretend.call(),
        ]
        assert response.json.calls == [
            pretend.call(),
            pretend.call(),
            pretend.call(),
            pretend.call(),
            pretend.call(),
        ]

    def test_rstuf_factory(self, db_request):
        db_request.registry.settings = {"rstuf.api_url": "http://rstuf"}
        rstuf = services.rstuf_factory(pretend.stub(), db_request)

        assert isinstance(rstuf, RSTUFService)
