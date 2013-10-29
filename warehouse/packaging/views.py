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
from __future__ import absolute_import, division, print_function
from __future__ import unicode_literals

import jinja2

from recliner import htmlize
from werkzeug.exceptions import NotFound

from warehouse.helpers import url_for
from warehouse.utils import cache, fastly, redirect, render_response


@cache("project_detail")
@fastly("project-detail", "project-detail~{project_name!n}")
def project_detail(app, request, project_name, version=None):
    # Get the real project name for this project
    project = app.models.packaging.get_project(project_name)

    if project is None:
        raise NotFound("Cannot find a project named {}".format(project_name))

    # Look up the version of the given project
    versions = app.models.packaging.get_project_versions(project.name)

    if not versions:
        # If there are no versions then we need to return a simpler response
        # that simply states the project exists but that there is no versions
        # registered.
        raise NotFound(
            "There are no versions registered for the {} project".format(
                project.name,
            ),
        )

    if project.name != project_name:
        # We've found the project, and the version exists, but the project name
        # isn't quite right so we'll redirect them to the correct one.
        return redirect(
            url_for(
                request,
                "warehouse.packaging.views.project_detail",
                project_name=project.name,
                version=version,
            ),
            code=301,
        )

    if version is None:
        # If there's no version specified, then we use the latest version
        version = versions[0]
    elif not version in versions:
        # If a version was specified then we need to ensure it's one of the
        # versions this project has, else raise a NotFound
        raise NotFound(
            "Cannot find the {} version of the {} project".format(
                version,
                project.name,
            ),
        )

    # Get the release data for the version
    release = app.models.packaging.get_release(project.name, version)

    # Render the project description
    description_html = htmlize(release["description"])

    # If our description wasn't able to be rendered, wrap it in <pre></pre>
    if not description_html.rendered:
        description_html = "<pre>" + description_html + "</pre>"

    # Mark our description_html as safe as it's already been cleaned by bleach
    description_html = jinja2.Markup(description_html)

    return render_response(
        app, request, "projects/detail.html",
        project=project,
        release=release,
        releases=app.models.packaging.get_releases(project.name),
        versions=versions,
        description_html=description_html,
        download_counts=app.models.packaging.get_download_counts(project.name),
        downloads=app.models.packaging.get_downloads(project.name, version),
        classifiers=app.models.packaging.get_classifiers(
            project.name,
            version,
        ),
        documentation=app.models.packaging.get_documentation_url(project.name),
        bugtracker=app.models.packaging.get_bugtrack_url(project.name),
        maintainers=app.models.packaging.get_users_for_project(project.name),
    )
