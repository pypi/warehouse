# SPDX-License-Identifier: Apache-2.0

import pytest

from sqlalchemy.orm import object_session

from warehouse.db import Model
from warehouse.utils.db.orm import NoSessionError, orm_session_from_obj


def test_orm_session_from_obj_raises_with_no_session():

    class FakeObject(Model):
        __tablename__ = "fake_object"

    obj = FakeObject()
    # Confirm that the object does not have a session with the built-in
    assert object_session(obj) is None

    with pytest.raises(NoSessionError):
        orm_session_from_obj(obj)
