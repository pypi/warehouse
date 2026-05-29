# SPDX-License-Identifier: Apache-2.0

import pretend

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

    def test_exc_with_missing_message(self, monkeypatch):
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda message: None)
        )
        monkeypatch.setattr(utils, "sentry_sdk", sentry_sdk)
        exc = utils._exc_with_message(HTTPBadRequest, "")
        assert isinstance(exc, HTTPBadRequest)
        assert exc.status_code == 400
        assert exc.status == "400 Bad Request"
        assert sentry_sdk.capture_message.calls == [
            pretend.call("Attempting to _exc_with_message without a message")
        ]
