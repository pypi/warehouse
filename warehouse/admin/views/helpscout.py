# SPDX-License-Identifier: Apache-2.0

import base64
import hashlib
import hmac

from email_validator import EmailNotValidError, validate_email
from pyramid.view import view_config
from pyramid_jinja2 import IJinja2Environment
from sqlalchemy.sql import func

from warehouse.accounts.models import Email

NO_USER_FOUND_RESPONSE = {
    "html": '<span class="badge pending">No PyPI user found</span>'
}


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

    # Validate input email per RFC 5321
    email_input = request.json_body.get("customer", {}).get("email", "")
    try:
        validated = validate_email(email_input, check_deliverability=False)
    except EmailNotValidError:
        return NO_USER_FOUND_RESPONSE

    # Strip subaddress (e.g., user+tag@domain.com -> user@domain.com)
    local_part = validated.local_part.split("+", 1)[0]
    normalized_email = f"{local_part}@{validated.domain}"

    # Find users whose email matches (also stripping any subaddress from stored emails)
    emails = (
        request.db.query(Email)
        .where(
            func.regexp_replace(Email.email, r"\+[^@]*@", "@").ilike(normalized_email)
        )
        .all()
    )

    if not emails:
        return NO_USER_FOUND_RESPONSE

    env = request.registry.queryUtility(IJinja2Environment, name=".jinja2")
    context = {"users": [e.user for e in emails]}
    template = env.get_template("admin/templates/admin/helpscout/app.html")
    content = template.render(**context, request=request)

    return {"html": content}
