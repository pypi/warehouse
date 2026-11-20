# SPDX-License-Identifier: Apache-2.0


class InvalidApiKeyError(Exception): ...


class ApiKeyLimitError(Exception):
    """The user already holds the most active keys allowed."""


class ApiKeyNameInUseError(Exception):
    """The user has an active key with this name, ignoring case."""
