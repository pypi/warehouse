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

    print("DEBUG: MBACCHI: starting get_contributors")
    api_url = "https://api.github.com"

    contributors = {}

    # FIXME
    # replace with one generated by PyPa personnel
    access_token = "INSERT_GITHUB_ACCESS_TOKEN"

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
        print(e)

    # print("contributors dict:")
    # for key, val in contributors.items():
    #     print("{}: {} {}".format(key, val["name"], val["html_url"]))

    query = request.db.query(Contributor.id, Contributor.contributor_login, Contributor.contributor_name, Contributor.contributor_url).all()
    # for id1, login, name, url in query:
    #     print("query return: {}:{}:{}:{}".format(id1, login, name, url))
    # print("query returns {}".format(query))
    clist = []
    print("query field 1:")
    print("length: {}".format(len(query)))
    # for i in range(len(query)):
    #     print("{}".format(query[i][1]))
    new_users = list(set(contributors.keys()).difference([q[1] for q in query]))

    print("New users length: {}".format(len(new_users)))
    for item in new_users:
        print("{}".format(item))

    for username in new_users:
        # print('Creating Contributor object for username: {}'.format(username))

        print("Adding items from contributors.items() using request.db.add")
        request.db.add(
            Contributor(contributor_login=username,
                        contributor_name=contributors[username]["name"],
                        contributor_url=contributors[username]["html_url"])
        )
        # request.db.commit()

    # for key, val in contributors.items():
    #     if key not in query
        #### NEW IDEA FROM DAVE/ADAM
        # Add users if they do not already exist in the db

        # pseudo code:
        # query db
        # if contributor login not in contributors.items()
        #   add to list
        # add list to db

        # print("{}: {}: {}".format(key, val["name"], val["url"]))
        #print("Adding {} to db".format(key))
        # Here we are going to update all items
        # so add all items to the list
        # item = Contributor(contributor_login=key,
        #                      contributor_name=val["name"],
        #                      contributor_url=val["html_url"])

        # for id1, login, name, url in query:
        #     # print("working on {}:{}:{}".format(login, name, url))
        #     to_update = [
        #         {"id": id1, "contributor_login": key, "contributor_name": val["name"],
        #          "contributor_url": val["html_url"]}
        #     ]


        # clist.append(item)
        # try adding to db here:
        # print("Adding items from contributors.items() using request.db.add")
        # request.db.add(
        #     Contributor(contributor_login=key,
        #                 contributor_name=val["name"],
        #                 contributor_url=val["html_url"])
        # )
    #     session.add(item)
    #
    # request.db.commit()
    # print("done...Printing list")
    # for x in clist:
    #     print(x)
    #
    # print("clist is a {}".format(type(clist)))
    # print("Adding items in to_update to db using bulk_update_mappings()")
    # request.db.bulk_update_mappings(Contributor, to_update)
    # request.db.bulk_save_objects(clist)

    # HOW DO I ADD TO THE DB? USING SOMETHING LIKE packaging/tasks.py ???
    # Reflect out updated ZScores into the database.
    # request.db.bulk_update_mappings(Project, to_update)

    return 0


# def includeme(config):
#     # Add a periodic task to get contributors every 2 hours, to do this we
#     # require the Github access token owned by the pypa warehouse application.
#     # if config.get_settings().get("warehouse.github_access_token"):
#     #     config.add_periodic_task(crontab(minute=0, hour='*/2'), get_contributors)
#
#     # TEST FIXME
#     # for now do every 10 minutes for testing purposes
#     #if config.get_settings().get("warehouse.github_access_token"):
#     config.add_periodic_task(crontab(minute='*/10'), get_contributors)
