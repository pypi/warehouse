# SPDX-License-Identifier: Apache-2.0

from collections.abc import Mapping, Sequence

from pyramid.threadlocal import get_current_request


def _adapt_v1(data: Mapping) -> Sequence | None:
    permissions = data.get("permissions")

    # This would be a malformed token, so we'll just refuse
    # to adapt it.
    if permissions is None:
        return None

    # Our V1 token didn't have a way to specify that a token should be
    # restricted to a specific user, just that it was scoped to "the user",
    # which the user was whoever the token was linked to in the database.
    # Our new tokens strengthens that to validate that the linked user
    # matches who it is expected to be, but since we don't have that
    # data for V1 tokens, we'll just use the current user.
    if permissions == "user":
        request = get_current_request()

        # If we don't have a current request, then we can't validate this
        # token.
        if request is None:
            return None

        # If we don't have a user associated with this request, then we
        # can't validate this token.
        if request.user is None:
            return None

        return [3, str(request.user.id)]
    # Our project level permissions for V1 caveats had a dictionary, with
    # the key "projects", and that was a list of normalized project names.
    elif isinstance(permissions, Mapping) and "projects" in permissions:
        return [1, permissions["projects"]]

    # If we get to here, then we don't know how to adapt this token, so
    # we'll just return None.
    return None


def _adapt_expiry(data: Mapping) -> Sequence | None:
    return [0, data["exp"], data["nbf"]]


def _adapt_project_ids(data: Mapping) -> Sequence | None:
    return [2, data["project_ids"]]


def adapt(data: Mapping) -> Sequence | None:
    # Check for our previous `V1Caveat` type.
    if data.get("version") == 1:
        return _adapt_v1(data)

    # Check for our previous `ExpiryCaveat` type.
    if "exp" in data and "nbf" in data:
        return _adapt_expiry(data)

    # Check for our previous `ProjectIDsCaveat` type.
    if "project_ids" in data:
        return _adapt_project_ids(data)

    # We don't have any other caveat types, so we don't know how to adapt
    # this payload.
    return None
