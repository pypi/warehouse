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


@view_config(route_name="credits", renderer="pages/credits.html", has_translations=True)
def credits_page(request):

    # get all items from Contributors table
    contributors = request.db.query(Contributor).order_by(Contributor.contributor_name)

    contrib_count = contributors.count()

    # In order to display all the names on the page, we split
    # them into two columns, so here we calculate the number of
    # items to place in each array.
    if contrib_count % 2 == 0:
        size = int(contrib_count / 2)
    else:
        size = int(contrib_count / 2 + 1)

    separated = [contributors[i : i + size] for i in range(0, contrib_count, size)]

    return {"contributors": separated}
