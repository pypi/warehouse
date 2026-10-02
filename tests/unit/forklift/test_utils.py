# SPDX-License-Identifier: Apache-2.0

from pyramid.httpexceptions import HTTPBadRequest

from warehouse.forklift import utils


class TestExcWithMessage:
    def test_exc_with_message(self):
        exc = utils._exc_with_message(HTTPBadRequest, "My Test Message.")
        assert isinstance(exc, HTTPBadRequest)
        assert exc.status_code == 400
        assert exc.status == "400 My Test Message."

    def test_exc_with_exotic_message(self):
        exc = utils._exc_with_message(
            HTTPBadRequest, "look at these wild chars: аÃ¤â€—"
        )
        assert isinstance(exc, HTTPBadRequest)
        assert exc.status_code == 400
        assert exc.status == "400 look at these wild chars: ?Ã¤â??"

    def test_exc_with_message_sanitizes_newlines(self):
        exc = utils._exc_with_message(
            HTTPBadRequest,
            "Invalid file\r\nX-Injected: yes",
        )

        assert exc.status == "400 Invalid file  X-Injected: yes"
        assert "\r" not in exc.status
        assert "\n" not in exc.status

    def test_exc_with_missing_message(self, mocker):
        capture_message = mocker.patch.object(
            utils.sentry_sdk, "capture_message", autospec=True
        )
        exc = utils._exc_with_message(HTTPBadRequest, "")
        assert isinstance(exc, HTTPBadRequest)
        assert exc.status_code == 400
        assert exc.status == "400 Bad Request"
        capture_message.assert_called_once_with(
            "Attempting to _exc_with_message without a message"
        )
