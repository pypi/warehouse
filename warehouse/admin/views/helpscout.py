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

import base64
import hashlib
import hmac
import re

from pyramid.view import view_config
from pyramid_jinja2 import IJinja2Environment
from sqlalchemy.sql import func

from warehouse.accounts.models import Email


def validate_helpscout_signature(request):
    signature = request.headers.get("X-HelpScout-Signature")
    secret = request.registry.settings.get("admin.helpscout.app_secret")
    if secret is None or signature is None:
        return False

    digest = hmac.digest(secret.encode(), request.body, hashlib.sha1)
    return hmac.compare_digest(digest, base64.b64decode(signature))


@view_config(
    route_name="admin.helpscout",
    renderer="json",
    require_methods=["POST"],
    require_csrf=False,
    uses_session=False,
)
def helpscout(request):
    """Integration for user details in Help Scout UI."""
    if not validate_helpscout_signature(request):
        request.response.status = 403
        return {"Error": "NotAuthorized"}

    email = (
        request.db.query(Email)
        .where(
            func.regexp_replace(Email.email, r"\+[^)]*@", "@").ilike(
                re.sub(
                    r"\+[^)]*@",
                    "@",
                    request.json_body.get("customer", {}).get("email", ""),
                )
            )
        )
        .all()
    )

    if len(email) == 0:
        return {"html": '<span class="badge pending">No PyPI user found</span>'}

    env = request.registry.queryUtility(IJinja2Environment, name=".jinja2")
    context = {"users": [e.user for e in email]}
    template = env.get_template("admin/templates/admin/helpscout/app.html")
    content = template.render(**context, request=request)

    return {"html": content}
