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

from pyramid.httpexceptions import HTTPGone, HTTPMovedPermanently, HTTPNotFound
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
        .filter(Classifier.deprecated.is_(False))
        .order_by(Classifier.classifier)
        .all()
    )

    return Response(
        text='\n'.join(c[0] for c in classifiers),
        content_type='text/plain; charset=utf-8'
    )


@view_config(route_name='legacy.api.pypi.search')
def search(request):
    return HTTPMovedPermanently(
        request.route_path(
            'search', _query={'q': request.params.get('term')}
        )
    )


@view_config(route_name='legacy.api.pypi.browse')
def browse(request):
    classifier_id = request.params.get('c')

    if not classifier_id:
        raise HTTPNotFound

    # Guard against the classifier_id not being a valid integer
    try:
        int(classifier_id)
    except ValueError:
        raise HTTPNotFound

    classifier = request.db.query(Classifier).get(classifier_id)

    if not classifier:
        raise HTTPNotFound

    return HTTPMovedPermanently(
        request.route_path(
            'search', _query={'c': classifier.classifier}
        )
    )


@view_config(route_name='legacy.api.pypi.files')
def files(request):
    name = request.params.get('name')
    version = request.params.get('version')

    if (not name) or (not version):
        raise HTTPNotFound

    return HTTPMovedPermanently(
        request.route_path(
            'packaging.release', name=name, version=version, _anchor="files"
        )
    )


@view_config(route_name='legacy.api.pypi.display')
def display(request):
    name = request.params.get('name')
    version = request.params.get('version')

    if not name:
        raise HTTPNotFound

    if version:
        return HTTPMovedPermanently(
            request.route_path(
                'packaging.release', name=name, version=version
            )
        )
    return HTTPMovedPermanently(
        request.route_path(
            'packaging.project', name=name
        )
    )
