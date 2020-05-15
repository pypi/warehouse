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

import json
import logging

import requests

from warehouse import tasks

from .contributors import Contributor

logger = logging.getLogger(__name__)


def call_github_api(url, headers):
    try:
        r = requests.get(url, headers=headers)
    except requests.exceptions.RequestException as e:
        raise Exception(e)

    if r.status_code is 200:
        return r


@tasks.task(ignore_result=True, acks_late=True)
def get_contributors(request):

    api_url = "https://api.github.com"

    contributors = {}

    access_token = request.registry.settings["warehouse.github_access_token"]

    headers = {"Accept": "application/vnd.github+json"}
    headers["Authorization"] = "token " + access_token

    initial_url = (
        api_url + "/repos/pypa/warehouse/contributors" + "?page=1&per_page=100"
    )

    r = call_github_api(initial_url, headers)

    # This might occur if GitHub API rate limit is reached, for example
    if r is None:
        logging.warning(
            "Error contacting GitHub API, cannot get warehouse contributors list"
        )
        return None

    next_request = ""

    # The GitHub API returns paginated results of 100 items maximum per
    # response. We will loop until the next link header is not returned
    # in the response header. This is documented here:
    # https://developer.github.com/v3/#pagination
    while next_request is not None:
        if r.status_code is 200:
            json_data = json.loads(r.text)
            for item in json_data:
                users_query = api_url + "/users/" + item["login"]
                r2 = call_github_api(users_query, headers)
                if r2.status_code is 200:
                    json_data2 = json.loads(r2.text)
                    if json_data2["name"] is None or len(json_data2["name"]) < 2:
                        json_data2["name"] = item["login"]
                    contributors[item["login"]] = {
                        "name": json_data2["name"],
                        "html_url": item["html_url"],
                    }
                else:
                    print(
                        "Error in request to /users/ endpoint: "
                        "Status code: {} Error: ".format(
                            r2.status_code, r2.raise_for_status()
                        )
                    )
        else:
            print(
                "Error in request to /contributors/ endpoint: "
                "Status code: {} Error: ".format(r.status_code, r.raise_for_status())
            )

        if r.links.get("next"):
            next_request = r.links["next"]["url"]
            r = call_github_api(next_request, headers)
        else:
            next_request = None

    # Get the list of contributors from the db, compare them to the list
    # from GitHub, add new items to the db
    query = request.db.query(
        Contributor.id,
        Contributor.contributor_login,
        Contributor.contributor_name,
        Contributor.contributor_url,
    ).all()

    new_users = list(set(contributors.keys()).difference([q[1] for q in query]))

    for username in new_users:
        request.db.add(
            Contributor(
                contributor_login=username,
                contributor_name=contributors[username]["name"],
                contributor_url=contributors[username]["html_url"],
            )
        )

    # Update any name fields in the db that are different from GitHub
    query2 = request.db.query(Contributor).all()

    for item in query2:
        item.contributor_name = contributors[item.contributor_login]["name"]

    request.db.bulk_save_objects(query2)

    return 0
