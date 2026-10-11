# SPDX-License-Identifier: Apache-2.0

"""ORM utilities."""

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.orm import Session, object_session

# Collections that only hold audit records: `events` (HasEvents),
# `observations` (HasObservations) and `invitations` (role invitations, rendered
# only on the private manage UI and admin pages). Appending to one marks the
# parent dirty, but nothing cached or indexed is derived from them.
AUDIT_ONLY_ATTRS = frozenset({"events", "observations", "invitations"})


class NoSessionError(Exception):
    """Raised when there is no active SQLAlchemy session"""


def orm_session_from_obj(obj) -> Session:
    """
    Returns the session from the ORM object.

    Adds guard, but it should never happen.
    The guard helps with type hinting, as the object_session function
    returns Optional[Session] type.
    """
    session = object_session(obj)
    if not session:
        raise NoSessionError("Object does not have a session")
    return session


def changed_attributes(obj, dirty) -> set[str]:
    """
    Returns the names of the attributes changed on ``obj``, or an empty set when
    it is not dirty or not a mapped instance.

    ``dirty`` is the session's dirty set. ``Session.dirty`` builds a new set on
    every access, so callers looping over a flush read it once and pass it in.
    """
    if obj not in dirty:
        return set()
    try:
        return set(sa_inspect(obj).committed_state.keys())
    except NoInspectionAvailable:
        return set()


def has_only_audit_changes(obj, dirty) -> bool:
    """
    Returns True when a dirty object changed only in `AUDIT_ONLY_ATTRS`, so
    nothing derived from it needs purging or reindexing.
    """
    changed = changed_attributes(obj, dirty)
    return bool(changed) and changed <= AUDIT_ONLY_ATTRS
