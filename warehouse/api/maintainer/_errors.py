# SPDX-License-Identifier: Apache-2.0

from datetime import datetime


class InvalidApiKeyError(Exception): ...


class ExpiredApiKeyError(InvalidApiKeyError):
    def __init__(self, expired: datetime):
        super().__init__(f"API key expired at {expired.isoformat()}")
        self.expired = expired
