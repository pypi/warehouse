# SPDX-License-Identifier: Apache-2.0

"""ORM utilities."""

from sqlalchemy.orm import Session, object_session


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
