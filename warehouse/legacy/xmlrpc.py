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

import re
from SimpleXMLRPCServer import SimpleXMLRPCDispatcher

from werkzeug.exceptions import BadRequest

from warehouse.http import Response


def handle_request(app, request):
    '''Wrap an invocation of the XML-RPC dispatcher.
    '''
    dispatcher = SimpleXMLRPCDispatcher()
    dispatcher.register_instance(Interface(app, request))

    # read in the XML-RPC request data, limiting to a sensible size
    if int(request.headers['Content-Length']) > 10 * 1024 * 1024:
        raise BadRequest('request data too large')
    xml_request = request.get_data(cache=False, as_text=True)

    # errors here are handled by _marshaled_dispatch
    response = dispatcher._marshaled_dispatch(xml_request)
    # legacy; remove non-printable ASCII control codes from the response
    response = re.sub('([\x00-\x08]|[\x0b-\x0c]|[\x0e-\x1f])+', '', response)

    return Response(response, mimetype="text/xml")


class Interface(object):
    def __init__(self, app, request):
        self.app = app
        self.request = request

    def list_packages(self):
        '''Retrieve a list of the package names registered with the package
        index.

        Returns a list of name strings.
        '''
        projects = self.app.models.packaging.all_projects()
        return [project.name for project in projects]

    def list_packages_with_serial(self):
        return self.app.models.packaging.get_packages_with_serial()
