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


def pagination_serializer(schema, data, route, request):
    extra_filters = ""
    for key, value in request.params.items():
        if key != "page":
            extra_filters = "{filters}&{key}={value}".format(
                filters=extra_filters, key=key, value=value
            )
    resource_url = request.route_url(route)
    url_template = "{url}?page={page}{extra_filters}"

    next_page = None
    if data.next_page:
        next_page = url_template.format(
            url=resource_url, page=data.next_page, extra_filters=extra_filters
        )
    previous_page = None
    if data.previous_page:
        previous_page = url_template.format(
            url=resource_url, page=data.previous_page, extra_filters=extra_filters
        )

    return {
        "data": schema.dump(data),
        "links": {"next_page": next_page, "previous_page": previous_page},
    }
