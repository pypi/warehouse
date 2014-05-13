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

from werkzeug.routing import Rule, EndpointPrefix, Submount

urls = [
    EndpointPrefix("warehouse.legacy.simple.", [
        Submount("/simple", [
            Rule("/", methods=["GET"], endpoint="index"),
            Rule("/<project_name>/", methods=["GET"], endpoint="project"),
        ]),
        Rule("/packages/<path:path>", methods=["GET"], endpoint="package"),
    ]),
    EndpointPrefix("warehouse.legacy.pypi.", [
        Rule("/pypi", methods=["GET", "POST"], endpoint="pypi"),
        Rule("/pypi/<project_name>/json", methods=["GET"],
             endpoint="project_json"),
        Rule("/pypi/<project_name>/<version>/json", methods=["GET"],
             endpoint="project_json"),
        Rule("/daytime", methods=["GET"], endpoint="daytime"),
    ]),
    EndpointPrefix("warehouse.legacy.xmlrpc.", [
        Rule("/_legacy/xmlrpc/", methods=["POST"], endpoint="handler"),
    ]),
]
