# SPDX-License-Identifier: Apache-2.0

# We want to allow Cross-Origin requests here so that users can interact
# with these endpoints via XHR/Fetch APIs in the browser.
_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": ", ".join(
        [
            "Content-Type",
            "If-Match",
            "If-Modified-Since",
            "If-None-Match",
            "If-Unmodified-Since",
        ]
    ),
    "Access-Control-Allow-Methods": "GET",
    "Access-Control-Max-Age": "86400",  # 1 day.
    "Access-Control-Expose-Headers": ", ".join(["X-PyPI-Last-Serial"]),
}
