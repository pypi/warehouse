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

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.view import view_config

from sqlalchemy.sql import select

from warehouse.accounts.tables import emails, users


@view_config(route_name="accounts.profile", renderer="accounts/profile.html")
def profile(request, username):
    res = yield from request.db.execute(
        select([
            users.c.id,
            users.c.username,
            users.c.name,
            users.c.date_joined,
            emails.c.email,
        ])
        .select_from(users.outerjoin(emails))
        .where(users.c.username == username)
        .limit(1)
    )
    user = yield from res.first()

    if user is None:
        raise HTTPNotFound("Could not find user {}".format(username))

    if user["username"] != username:
        return HTTPMovedPermanently(
            request.current_route_url(username=user["username"]),
        )

    return {"user": user}
