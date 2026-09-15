# SPDX-License-Identifier: Apache-2.0

import sentry_sdk


def _exc_with_message(exc, message, **kwargs):
    if not message:
        sentry_sdk.capture_message("Attempting to _exc_with_message without a message")

    # The crappy old API that PyPI offered uses the status to pass down
    # messages to the client. So this function will make that easier to do.
    resp = exc(detail=message, **kwargs)
    # We need to guard against characters outside of iso-8859-1 per RFC.
    # Specifically here, where user-supplied text may appear in the message,
    # which our WSGI server may not appropriately handle (indeed gunicorn does not).
    status_message = message.encode("iso-8859-1", "replace").decode("iso-8859-1")
    resp.status = f"{resp.status_code} {status_message}"
    return resp
