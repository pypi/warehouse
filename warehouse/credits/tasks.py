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

import logging

import github3

from warehouse import tasks

from .contributors import Contributor

logger = logging.getLogger(__name__)


@tasks.task(ignore_result=True, acks_late=True)
def get_contributors(request):

    # Try to reduce verbosity of github3.py output
    logger.setLevel(logging.ERROR)

    # list of contributor logins that should be ignored
    ignore_bots = [
        "dependabot[bot]",
        "dependabot-preview[bot]",
        "github-actions[bot]",
        "pyup-bot",
        "requires",
        "weblate",
    ]

    contributors = {}

    access_token = request.registry.settings.get("github.token")

    if access_token is None:
        return 1

    github = github3.login(token=access_token)
    repo = github.repository("pypa", "warehouse")
    for c in repo.contributors():
        u = github.user(c)
        print(f"u: {u}: u.name: {u.name}; u.html_url: {u.html_url}")
        if u.login in ignore_bots:
            print(f"ignoring bot user {u.login}")
            continue
        if u.name is None or len(u.name) < 2:
            u.name = u.login

        contributors[u.login] = {
            "name": u.name,
            "html_url": u.html_url,
        }

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
        print(f"adding new user to contributors table: {username}")
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
