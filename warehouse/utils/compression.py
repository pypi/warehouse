# SPDX-License-Identifier: Apache-2.0

import base64
import hashlib

from collections.abc import Sequence

ENCODINGS = ["identity", "gzip"]
DEFAULT_ENCODING = "identity"
BUFFER_MAX = 1 * 1024 * 1024  # We'll buffer up to 1MB


def _compressor(request, response):
    # Skip items with a Vary: Cookie/Authorization Header because we don't know
    # if they are safe from the CRIME attack.
    if response.vary is not None and (set(response.vary) & {"Cookie", "Authorization"}):
        return

    # Avoid compression if we've already got a Content-Encoding.
    if "Content-Encoding" in response.headers:
        return

    # Ensure that the Accept-Encoding header gets added to the response.
    vary = set(response.vary if response.vary is not None else [])
    vary.add("Accept-Encoding")
    response.vary = vary

    # Negotiate the correct encoding from our request.
    target_encoding = request.accept_encoding.best_match(
        ENCODINGS, default_match=DEFAULT_ENCODING
    )

    # If we have a Sequence, we'll assume that we aren't streaming the
    # response because it's probably a list or similar.
    streaming = not isinstance(response.app_iter, Sequence)

    # If our streaming content is small enough to easily buffer in memory
    # then we'll just convert it to a non streaming response.
    if (
        streaming
        and response.content_length is not None
        and response.content_length <= BUFFER_MAX
    ):
        response.body
        streaming = False

    if streaming:
        response.encode_content(encoding=target_encoding, lazy=True)

        # We need to remove the content_length from this response, since
        # we no longer know what the length of the content will be.
        response.content_length = None

        # If this has a streaming response, then we need to adjust the ETag
        # header, if it has one, so that it reflects this. We don't just append
        # ;gzip to this because we don't want people to try and use it to infer
        # any information about it.
        if response.etag is not None:
            md5_digest = hashlib.md5(
                (response.etag + ";gzip").encode("utf8"), usedforsecurity=False
            )
            md5_digest = md5_digest.digest()
            md5_digest = base64.b64encode(md5_digest)
            md5_digest = md5_digest.replace(b"\n", b"").decode("utf8")
            response.etag = md5_digest.strip("=")
    else:
        original_length = len(response.body)
        response.encode_content(encoding=target_encoding, lazy=False)

        # If the original length is less than our new, compressed length
        # then we'll go back to the original. There is no reason to encode
        # the content if it increases the length of the body.
        if original_length < len(response.body):
            response.decode_content()

        # If we've added an encoding to the content, then we'll want to
        # recompute the ETag.
        if response.content_encoding is not None:
            response.md5_etag()


def compression_tween_factory(handler, registry):
    def compression_tween(request):
        response = handler(request)

        # We use a response callback here so that it happens after all of the
        # other response callbacks are called. This is important because
        # otherwise we won't be able to check Vary headers and such that are
        # set by response callbacks.
        request.add_response_callback(_compressor)

        return response

    return compression_tween
