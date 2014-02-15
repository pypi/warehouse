# Copyright 2013 Donald Stufft
#
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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import json
import time

from warehouse.helpers import url_for
from werkzeug.utils import redirect
from warehouse.http import Response
from werkzeug.exceptions import NotFound, BadRequest

from warehouse.legacy import xmlrpc
from warehouse.utils import is_valid_json_callback_name


def pypi(app, request):
    # if the MIME type of the request is XML then we go into XML-RPC mode
    if request.headers.get('Content-Type') == 'text/xml':
        return xmlrpc.handle_request(app, request)

    # no XML-RPC and no :action means we render the index, or at least we
    # redirect to where it moved to
    return redirect(
        url_for(
            request,
            "warehouse.views.index",
        ),
        code=301,
    )


def daytime(app, request):
    response = time.strftime("%Y%m%dT%H:%M:%S\n", time.gmtime(time.time()))
    return Response(response, mimetype="text/plain")


# @cache("simple")
# @fastly("simple", "simple~{project_name!n}")
def project_json(app, request, project_name):
    # fail early if callback is invalid
    callback = request.args.get('callback')
    if callback:
        if not is_valid_json_callback_name(callback):
            raise BadRequest('invalid JSONP callback name')

    # Get the real project name for this project
    project = app.models.packaging.get_project(project_name)

    if project is None:
        raise NotFound("{} does not exist".format(project_name))

    # we're looking for the latest version
    versions = app.models.packaging.get_project_versions(project.name)
    if not versions:
        raise NotFound("{} has no releases".format(project.name))
    version = versions[0]

    rpc = xmlrpc.Interface(app, request)

    d = dict(
        info=rpc.release_data(project.name, version),
        urls=rpc.release_urls(project.name, version),
    )
    for url in d['urls']:
        url['upload_time'] = url['upload_time'].strftime('%Y-%m-%dT%H:%M:%S')

    data = json.dumps(d)

    # write the JSONP extra crap if necessary
    if callback:
        data = '/**/ %s(%s);' % (callback, data)

    response = Response(data, mimetype="application/json")
    response.headers['Content-Disposition'] = 'inline'
    return response
