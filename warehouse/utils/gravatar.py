# SPDX-License-Identifier: Apache-2.0

import hashlib
import urllib.parse


def _hash(email: str | None) -> str:
    if email is None:
        email = ""

    return hashlib.md5(
        email.strip().lower().encode("utf8"), usedforsecurity=False
    ).hexdigest()


def gravatar(request, email, size=80):
    url = f"https://secure.gravatar.com/avatar/{_hash(email)}"
    params = {"size": size}

    return request.camo_url("?".join([url, urllib.parse.urlencode(params)]))


def profile(email: str) -> str:
    return f"https://gravatar.com/{_hash(email)}"
