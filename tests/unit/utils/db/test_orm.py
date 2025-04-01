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
