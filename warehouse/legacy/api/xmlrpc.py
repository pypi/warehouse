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

import functools

from pyramid_rpc.xmlrpc import xmlrpc_method

from warehouse.packaging.models import Project


pypi_xmlrpc = functools.partial(xmlrpc_method, endpoint="pypi")


@pypi_xmlrpc(method="list_packages")
def list_packages(request):
    names = request.db.query(Project.name).order_by(Project.name).all()
    return [n[0] for n in names]
