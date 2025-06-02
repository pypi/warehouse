# SPDX-License-Identifier: Apache-2.0

from sqlalchemy.orm.exc import DetachedInstanceError


def make_repr(*attrs, _self=None):
    def _repr(self=None):
        if self is None and _self is not None:
            self = _self

        try:
            return "{}({})".format(
                self.__class__.__name__,
                ", ".join(f"{a}={repr(getattr(self, a))}" for a in attrs),
            )
        except DetachedInstanceError:
            return f"{self.__class__.__name__}(<detached>)"

    return _repr
