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
