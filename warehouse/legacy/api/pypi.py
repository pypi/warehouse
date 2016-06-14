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

from pyramid.httpexceptions import HTTPGone
from pyramid.response import Response
from pyramid.view import forbidden_view_config, view_config

from warehouse.classifiers.models import Classifier


def _exc_with_message(exc, message):
    # The crappy old API that PyPI offered uses the status to pass down
    # messages to the client. So this function will make that easier to do.
    resp = exc(message)
    resp.status = "{} {}".format(resp.status_code, message)
    return resp


@view_config(
    route_name="legacy.api.pypi.file_upload",
    require_csrf=False,
    require_methods=["POST"],
)
@view_config(
    route_name="legacy.api.pypi.submit",
    require_csrf=False,
    require_methods=["POST"],
)
@view_config(
    route_name="legacy.api.pypi.submit_pkg_info",
    require_csrf=False,
    require_methods=["POST"],
)
@view_config(
    route_name="legacy.api.pypi.doc_upload",
    require_csrf=False,
    require_methods=["POST"],
)
def forklifted(request):
    settings = request.registry.settings
    domain = settings.get(
        "forklift.domain",
        settings.get(
            "warehouse.domain",
            request.domain,
        ),
    )

    information_url = "TODO"

    return _exc_with_message(
        HTTPGone,
        ("This API has moved to https://{}/legacy/. See {} for more "
         "information.").format(domain, information_url),
    )


@view_config(route_name="legacy.api.pypi.doap")
def doap(request):
    return _exc_with_message(HTTPGone, "DOAP is no longer supported.")


@forbidden_view_config(request_param=":action")
def forbidden_legacy(exc, request):
    # We're not going to do anything amazing here, this just exists to override
    # the default forbidden handler we have which does redirects to the login
    # view, which we do not want on this API.
    return exc


@view_config(route_name="legacy.api.pypi.list_classifiers")
def list_classifiers(request):
    classifiers = (
        request.db.query(Classifier.classifier)
               .order_by(Classifier.classifier)
               .all()
    )

    return Response(
        text='\n'.join(c[0] for c in classifiers),
        content_type='text/plain; charset=utf-8'
    )
