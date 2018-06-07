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

from pyramid.view import view_config

from .contributors import Contributor


@view_config(route_name="credits", renderer="pages/credits.html")
def credits_page(request):

    # get all items from Contributors table
    contributors = request.db.query(Contributor).order_by(Contributor.contributor_name)

    contrib_count = contributors.count()

    # separate the list into two lists to be used in the two column layout
    separated = [
        contributors[0 : int(contrib_count / 2)],
        contributors[int(contrib_count / 2) : contrib_count],
    ]

    return {"contributors": separated}
