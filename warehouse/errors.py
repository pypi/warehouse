# SPDX-License-Identifier: Apache-2.0

from pyramid.security import Denied


class WarehouseDenied(Denied):
    def __new__(cls, s, *args, reason=None, **kwargs):
        inner = super().__new__(cls, s, *args, **kwargs)
        inner.reason = reason
        return inner
