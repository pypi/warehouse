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

from passlib.context import CryptContext
from sqlalchemy.orm.exc import NoResultFound
from zope.interface import implementer

from warehouse.accounts.interfaces import ILoginService
from warehouse.accounts.models import User


@implementer(ILoginService)
class DatabaseLoginService:

    def __init__(self, session):
        self.db = session
        self.hasher = CryptContext(
            schemes=[
                "bcrypt_sha256",
                "bcrypt",
                "django_bcrypt",
                "unix_disabled",
            ],
            deprecated=["auto"],
        )

    def find_userid(self, username):
        try:
            user = (
                self.db.query(User.id)
                    .filter(User.username == username)
                    .one()
            )
        except NoResultFound:
            return

        return user.id

    def check_password(self, userid, password):
        user = self.db.query(User).get(userid)
        if user is None:
            return False

        # Actually check our hash, optionally getting a new hash for it if
        # we should upgrade our saved hashed.
        ok, new_hash = self.hasher.verify_and_update(password, user.password)

        # Check if the password itself was OK or not.
        if not ok:
            return False

        # If we've gotten a new password hash from the hasher, then we'll want
        # to save that hash.
        if new_hash:
            user.password = new_hash

        return True


def database_login_factory(context, request):
    return DatabaseLoginService(request.db)
