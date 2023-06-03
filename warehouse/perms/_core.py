# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from dataclasses import dataclass
from typing import Any

from pyramid.authorization import Allow

# TODO: should permissions be case sensitive?


@dataclass
class _Permission:
    # The actual permission this represents
    permission: str
    # Any other permissions this permission can stand in for, used for "parent"
    # permissions or legacy aliases.
    other: list[str]
    # Whether this permission requires 2fa or not.
    requires_2fa: bool

    def __eq__(self, other):
        # If we're comparing against another permission object, then we'll
        # check to see if we have *any* overlap in permissions.
        if isinstance(other, _Permission):
            our_perms = set([self.permission] + self.other)
            their_perms = set([other.permission] + other.other)
            if our_perms & their_perms:
                return True
        # If we're comparing against a string, then we just need to see if the
        # string matches any of our valid permissions.
        elif isinstance(other, str):
            if other == self.permission or other in self.other:
                return True

        return False

    def __ne__(self, other):
        return not self.__eq__(other)


class _PermissionRegistry:
    _permissions = dict[str, _Permission]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._tags = {}

    def add(self, perm: _Permission) -> _Permission:
        if perm.permission in self._permissions:
            raise ValueError(f"Cannot re-use permission: {perm.permission}.")

        self._permissions[perm.permission] = perm

        return perm

    def lookup(self, /, perm: str) -> _Permission | None:
        return self._permissions.get(perm)


_permissions_registry = _PermissionRegistry()


def Permission(
    perm: str,
    other: list[str | _Permission] | None = None,
    *,
    requires_2fa: bool = False,
) -> str:
    if other is None:
        other = []

    # TODO: Flatten other into a list[str]
    # TODO: other should be required to be _Permission objects.

    perm_obj = _Permission(perm, other, requires_2fa=requires_2fa)
    return _permissions_registry.add(perm_obj)


def requires_2fa(perm: _Permission | str) -> bool:
    if isinstance(perm, str):
        lperm = _permissions_registry.lookup(perm=perm)
        if lperm is None:
            raise ValueError(f"unknown permission: {perm}")
        perm = lperm

    return perm.requires_2fa


def allow(principal: str, *perms: _Permission) -> tuple[str, str, list[str]]:
    permissions = [p.permission for p in perms]
    return (Allow, principal, permissions)
