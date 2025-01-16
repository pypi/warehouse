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

from json import JSONDecodeError

from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden
from pyramid.view import view_config

from warehouse.admin.flags import AdminFlagValue
from warehouse.authnz import Permissions
from warehouse.forklift.legacy import _exc_with_message

# TODO: Refactor these so they don't come from legacy.
from warehouse.legacy.api.json import _RELEASE_CACHE_DECORATOR, json_release
from warehouse.packaging.models import Release


@view_config(
    route_name="api.rest.release",
    context=Release,
    renderer="json",
    decorator=_RELEASE_CACHE_DECORATOR,
    request_method="GET",
)
def json_release_get(release, request):
    return json_release(release, request)


@view_config(
    route_name="api.rest.release",
    context=Release,
    renderer="json",
    decorator=_RELEASE_CACHE_DECORATOR,
    accept="application/json",
    request_method="PATCH",
    require_methods=["PATCH"],
    uses_session=True,
    # openapi=True,
    # api_version="api-v1",
    permission=Permissions.APIModify,
    require_csrf=False,
)
def json_release_modify(release, request):
    # Let API clients know if we're in read-only mode.
    if request.flags.enabled(AdminFlagValue.READ_ONLY):
        raise _exc_with_message(
            HTTPForbidden,
            "Read-only mode: Release modifications are temporarily disabled.",
        )

    data = json_release(release, request)
    if not request.body:
        # There's nothing to do.
        return data

    # TBD: Log this event?
    try:
        body = request.json_body
    except JSONDecodeError as error:
        raise _exc_with_message(HTTPBadRequest, str(error))

    # We're RESTful-ish here.  We don't really have a full API representation
    # of a Release, and for now we're only allowing API modifications to the
    # yank status of a release.  Hence, only allowing `yanked` and
    # `yanked_reason` attributes in a PATCH request, since PATCH allows partial
    # update to a resource representation.

    missing = object()
    # As per PEP 592, releases can be yanked and unyanked willy-nilly.
    yanked = body.get("yanked", missing)
    yanked_reason = body.get("yanked_reason", missing)

    # 2024-10-15(warsaw): Likely we should use jsonschema.validate() to
    # validate the data types read from the request body, but with the optional
    # semantics implemented below, it may not be worth it yet.

    # First we yank or unyank the release.
    if yanked is not missing:
        if not isinstance(yanked, bool):
            raise _exc_with_message(HTTPBadRequest, "`yanked` must be a boolean")
        release.yanked = yanked

    # Next, if the release is either being yanked or the yank status is not
    # being changed, but the release was already yanked, then the request can
    # modify the reason for the yanking.
    if not release.yanked:
        # When unyanking, remove any previous yank reason.
        #
        # 2024-10-15(warsaw): The question is whether we should even accept a
        # request that unyanks and provides a yank_reason, or doesn't change
        # the yank status of an already yanked release, but gives a yank
        # reason.  For consistency in the request packets between yanking and
        # unyanking, I'm choosing to ignore a yank_reason when the release is
        # unyanked, rather than raise an exception.
        release.yanked_reason = ""
    elif yanked_reason is not missing:
        if yanked_reason is None:
            yanked_reason = ""
        if not isinstance(yanked_reason, str):
            raise _exc_with_message(
                HTTPBadRequest, "`yanked_reason` must be a string or None"
            )
        release.yanked_reason = "" if yanked_reason is None else yanked_reason

    # Return the new JSON body of the release object.
    return json_release(release, request)
