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

import jinja2
import readme.rst

from werkzeug.exceptions import NotFound

from warehouse import fastly
from warehouse.helpers import url_for
from warehouse.templates import render_response
from warehouse.utils import cache, redirect, camouflage_images


@cache(browser=1, varnish=120)
@fastly.projects(project_name="project")
def project_detail(app, request, project_name, version=None):
    # Get the real project name for this project
    project = app.db.packaging.get_project(project_name)

    if project is None:
        raise NotFound("Cannot find a project named {}".format(project_name))

    # Look up all the releases for the given project
    releases = app.db.packaging.get_releases(project)

    if not releases:
        # If there are no releases then we need to return a simpler response
        # that simply states the project exists but that there is no versions
        # registered.
        raise NotFound(
            "There are no releases registered for the {} project".format(
                project,
            ),
        )

    if project != project_name:
        # We've found the project, and the version exists, but the project name
        # isn't quite right so we'll redirect them to the correct one.
        return redirect(
            url_for(
                request,
                "warehouse.packaging.views.project_detail",
                project_name=project,
                version=version,
            ),
            code=301,
        )

    if version is None:
        # If there's no version specified, then we use the latest version
        version = releases[0]["version"]
    elif version not in (r["version"] for r in releases):
        # If a version was specified then we need to ensure it's one of the
        # versions this project has, else raise a NotFound
        raise NotFound(
            "Cannot find the {} version of the {} project".format(
                version,
                project,
            ),
        )

    # Get the release data for the version
    release = app.db.packaging.get_release(project, version)

    # Get the number of reverse dependencies for this project
    project_url = lambda name: url_for(
        request, 'warehouse.packaging.views.project_detail',
        project_name=name)
    reverse_dependencies = [
        {'name': row['name'], 'url': project_url(row['name'])}
        for row in app.db.packaging.get_reverse_dependencies(project + ' %')
    ]

    if release.get("description"):
        # Render the project description
        description_html, rendered = readme.rst.render(release["description"])

        if not rendered:
            description_html = description_html.replace("\n", "<br>")

        if app.config.camo:
            description_html = camouflage_images(
                app.config.camo.url,
                app.config.camo.key,
                description_html,
            )
    else:
        description_html = ""

    # Mark our description_html as safe as it's already been cleaned by bleach
    description_html = jinja2.Markup(description_html)

    # Split the requirement string to (project name, the rest)
    requirements = []
    for req in release.get('requires_dist', []):
        project_name, *other = req.split(' ', 1)
        url = url_for(request, 'warehouse.packaging.views.project_detail',
                      project_name=project_name)
        requirements.append({
            'project_name': project_name,
            'project_url': url,
            'other': other[0] if other else ''
        })

    return render_response(
        app, request, "projects/detail.html",
        project=project,
        release=release,
        releases=releases,
        requirements=requirements,
        reverse_dependencies=reverse_dependencies,
        description_html=description_html,
        download_counts=app.db.packaging.get_download_counts(project),
        downloads=app.db.packaging.get_downloads(project, version),
        classifiers=app.db.packaging.get_classifiers(project, version),
        documentation=app.db.packaging.get_documentation_url(project),
        bugtracker=app.db.packaging.get_bugtrack_url(project),
        maintainers=app.db.packaging.get_users_for_project(project),
    )
