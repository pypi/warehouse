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
import requests
from time import sleep

from warehouse import tasks
from .contributors import Contributor


@tasks.task(ignore_result=True, acks_late=True)
def get_contributors(request):

    api_url = "https://api.github.com"

    contributors = {}

    access_token = request.registry.settings["warehouse.github_access_token"]

    try:
        r = requests.get(api_url + "/repos/pypa/warehouse/stats/contributors"
                         + "?access_token=" + access_token)
        if r.status_code is 200:
            json_data = json.loads(r.text)
            for item in json_data:
                r2 = requests.get(api_url + "/users/" + item["author"]["login"]
                                  + "?access_token=" + access_token)
                if r2.status_code is 200:
                    json_data2 = json.loads(r2.text)
                    if json_data2["name"] is None or len(json_data2["name"]) < 2:
                        json_data2["name"] = item["author"]["login"]
                    contributors[item["author"]["login"]] = {
                        "name": json_data2["name"],
                        "html_url": item["author"]["html_url"]}
                else:
                    print("Error in request: Status code: {} Error: ".format(
                        r2.status_code, r2.raise_for_status()))
        elif r.status_code is 202:
            # The status code can be 202 when statistics haven't yet been
            # cached by Github, in that case we will sleep and retry the
            # request. See:
            # https://developer.github.com/v3/repos/statistics/#a-word-about-caching
            sleep(30)
            get_contributors(request)
        else:
            print("Error in request: Status code: {} Error: ".format(
                r.status_code, r.raise_for_status()))
    except requests.exceptions.RequestException as e:
        raise Exception(e)

    # Get the list of contributors from the db and add new folks from GitHub
    query = request.db.query(Contributor.id, Contributor.contributor_login,
                             Contributor.contributor_name,
                             Contributor.contributor_url).all()

    new_users = list(set(contributors.keys()).difference([q[1] for q in query]))

    for username in new_users:
        # print("{}".format(item))
        request.db.add(
            Contributor(contributor_login=username,
                        contributor_name=contributors[username]["name"],
                        contributor_url=contributors[username]["html_url"])
        )

    # Update any name fields in the db that are different from GitHub
    query2 = request.db.query(Contributor).all()

    for item in query2:
        item.contributor_name = contributors[item.contributor_login]['name']

    request.db.bulk_save_objects(query2)

    return 0
