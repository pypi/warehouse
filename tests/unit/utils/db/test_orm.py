# SPDX-License-Identifier: Apache-2.0

import pytest

from sqlalchemy.orm import object_session

from tests.common.db.packaging import ProjectFactory
from warehouse.db import Model
from warehouse.utils.db.orm import (
    NoSessionError,
    changed_attributes,
    has_only_audit_changes,
    orm_session_from_obj,
)


def test_orm_session_from_obj_raises_with_no_session():

    class FakeObject(Model):
        __tablename__ = "fake_object"

    obj = FakeObject()
    # Confirm that the object does not have a session with the built-in
    assert object_session(obj) is None

    with pytest.raises(NoSessionError):
        orm_session_from_obj(obj)


def test_changed_attributes_not_dirty():
    """An object outside the dirty set has no changes to report."""
    assert changed_attributes(object(), dirty=set()) == set()


def test_changed_attributes_not_mapped():
    """A dirty object that SQLAlchemy cannot inspect reports no changes."""
    obj = object()
    assert changed_attributes(obj, dirty={obj}) == set()


def test_changed_attributes_mapped(db_request):
    """A dirty mapped object reports the names of its changed attributes."""
    project = ProjectFactory.create()
    db_request.db.flush()

    # record_event reads request.ip_address, which autoflushes, so it goes first
    project.record_event(tag="test:event", request=db_request, additional={})
    project.has_docs = True

    dirty = db_request.db.dirty
    assert changed_attributes(project, dirty) == {"has_docs", "events"}


def test_has_only_audit_changes(db_request):
    """Only an audit-only change set counts, not a mixed one or no changes."""
    project = ProjectFactory.create()
    db_request.db.flush()
    assert not has_only_audit_changes(project, db_request.db.dirty)

    project.record_event(tag="test:event", request=db_request, additional={})
    assert has_only_audit_changes(project, db_request.db.dirty)

    project.has_docs = True
    assert not has_only_audit_changes(project, db_request.db.dirty)
