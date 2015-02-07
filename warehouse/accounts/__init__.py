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
from pyramid.authentication import SessionAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy

from warehouse.accounts.models import User


def _pw_hasher(request):
    return request.registry["passwords"]


def _authenticate(userid, request):
    user = request.db.query(User).filter(User.id == userid).first()
    if user is None:
        return
    return []  # TODO: Add other principles.


def _user(request):
    user = request.db.query(User).filter(
        User.id == request.unauthenticated_userid
    ).first()

    if user is None:
        return  # TODO: We need some sort of Anonymous User.

    # TODO: We probably don't want to actually just return the database object,
    #       here.
    return user


def includeme(config):
    # Register our Password Handling
    config.registry["passwords"] = CryptContext(
        schemes=["bcrypt_sha256", "bcrypt", "django_bcrypt", "unix_disabled"],
        deprecated=["auto"],
    )
    config.add_request_method(_pw_hasher, name="password_hasher", reify=True)

    # Register our authentication and authorization policies
    config.set_authentication_policy(
        SessionAuthenticationPolicy(callback=_authenticate),
    )
    config.set_authorization_policy(ACLAuthorizationPolicy())

    # Add a request method which will allow people to access the user object.
    config.add_request_method(_user, name="user", reify=True)
